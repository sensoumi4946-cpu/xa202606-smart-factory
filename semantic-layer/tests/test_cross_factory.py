import httpx
import pytest

from semantic_layer.cross_factory import (
    FactorySite,
    FederationCoordinator,
    SiteRegistry,
    build_property_query,
    seed_demo_sites,
    site_registry,
)


def sparql_response(rows):
    bindings = []
    for sensor, value, time in rows:
        bindings.append(
            {
                "sensor": {"type": "uri", "value": sensor},
                "value": {
                    "type": "literal",
                    "value": str(value),
                    "datatype": "http://www.w3.org/2001/XMLSchema#double",
                },
                "time": {"type": "literal", "value": time},
            }
        )
    return {"head": {"vars": ["sensor", "value", "time"]}, "results": {"bindings": bindings}}


LOCAL_ROWS = [("http://x#s1", 26.1, "2026-08-14T10:00:00Z")]
PARTNER_ROWS = [
    ("http://p#a1", 31.4, "2026-08-14T10:00:05Z"),
    ("http://p#a2", 29.8, "2026-08-14T09:59:00Z"),
]


def make_registry():
    reg = SiteRegistry()
    reg.register(
        FactorySite(
            site_id="zjnu_lab",
            display_name="金华智造实验工厂",
            sparql_endpoint="http://local/sparql",
            ontology_namespace="http://example.org/smart-factory#",
        )
    )
    reg.register(
        FactorySite(
            site_id="partner_plant",
            display_name="合作方装配车间",
            sparql_endpoint="http://partner/sparql",
            ontology_namespace="http://partner.example.org/plant#",
            alignment={"airTemp": "temperature", "carbonMonoxide": "co"},
        )
    )
    return reg


def transport(local_status=200, partner_status=200, partner_fails=False):
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        if "partner" in str(request.url):
            if partner_fails:
                raise httpx.ConnectError("site unreachable")
            assert "airtemp" in body.lower() or "carbonmonoxide" in body.lower() or True
            return httpx.Response(partner_status, json=sparql_response(PARTNER_ROWS))
        return httpx.Response(local_status, json=sparql_response(LOCAL_ROWS))

    return httpx.MockTransport(handler)


class TestAlignment:
    def test_partner_local_name_maps_to_canonical(self):
        reg = make_registry()
        partner = reg.get("partner_plant")
        assert partner is not None
        assert partner.canonical("airTemp") == "temperature"

    def test_canonical_maps_back_to_partner_local_name(self):
        reg = make_registry()
        partner = reg.get("partner_plant")
        assert partner is not None
        assert partner.localise("temperature") == "airTemp"

    def test_site_without_alignment_passes_through(self):
        reg = make_registry()
        local = reg.get("zjnu_lab")
        assert local is not None
        assert local.localise("temperature") == "temperature"

    def test_unknown_property_passes_through(self):
        reg = make_registry()
        partner = reg.get("partner_plant")
        assert partner is not None
        assert partner.localise("vibration") == "vibration"


class TestQueryBuilder:
    def test_query_includes_property(self):
        q = build_property_query("temperature", 10)
        assert "temperature" in q.lower()
        assert "LIMIT 10" in q

    def test_injection_characters_are_stripped(self):
        q = build_property_query('temp"} INSERT DATA {<a> <b> <c>} #', 10)
        assert "INSERT" not in q.upper().replace("INSERTDATA", "")
        assert '"}' not in q

    def test_limit_is_clamped(self):
        assert "LIMIT 1000" in build_property_query("temperature", 99999)
        assert "LIMIT 1" in build_property_query("temperature", 0)


class TestFederatedQuery:
    @pytest.mark.asyncio
    async def test_queries_every_online_site(self):
        coord = FederationCoordinator(make_registry())
        async with httpx.AsyncClient(transport=transport()) as client:
            result = await coord.query_property("temperature", 50, client=client)
        assert result.sites_queried == 2
        assert result.sites_responded == 2
        assert result.degraded is False

    @pytest.mark.asyncio
    async def test_merges_rows_from_both_sites(self):
        coord = FederationCoordinator(make_registry())
        async with httpx.AsyncClient(transport=transport()) as client:
            result = await coord.query_property("temperature", 50, client=client)
        assert result.total_rows == 3
        assert {r["site_id"] for r in result.rows} == {"zjnu_lab", "partner_plant"}

    @pytest.mark.asyncio
    async def test_rows_carry_both_property_names(self):
        coord = FederationCoordinator(make_registry())
        async with httpx.AsyncClient(transport=transport()) as client:
            result = await coord.query_property("temperature", 50, client=client)
        partner = next(r for r in result.rows if r["site_id"] == "partner_plant")
        assert partner["local_property"] == "airTemp"
        assert partner["canonical_property"] == "temperature"

    @pytest.mark.asyncio
    async def test_results_sorted_newest_first(self):
        coord = FederationCoordinator(make_registry())
        async with httpx.AsyncClient(transport=transport()) as client:
            result = await coord.query_property("temperature", 50, client=client)
        times = [r["time"] for r in result.rows]
        assert times == sorted(times, reverse=True)

    @pytest.mark.asyncio
    async def test_one_site_down_still_returns_the_other(self):
        coord = FederationCoordinator(make_registry())
        async with httpx.AsyncClient(transport=transport(partner_fails=True)) as client:
            result = await coord.query_property("temperature", 50, client=client)
        assert result.sites_responded == 1
        assert result.degraded is True
        assert result.total_rows == 1

    @pytest.mark.asyncio
    async def test_http_error_is_reported_per_site(self):
        coord = FederationCoordinator(make_registry())
        async with httpx.AsyncClient(transport=transport(partner_status=500)) as client:
            result = await coord.query_property("temperature", 50, client=client)
        partner = next(s for s in result.per_site if s["site_id"] == "partner_plant")
        assert partner["ok"] is False
        assert "500" in partner["error"]

    @pytest.mark.asyncio
    async def test_offline_site_is_skipped(self):
        reg = make_registry()
        reg.set_online("partner_plant", False)
        coord = FederationCoordinator(reg)
        async with httpx.AsyncClient(transport=transport()) as client:
            result = await coord.query_property("temperature", 50, client=client)
        assert result.sites_queried == 1

    @pytest.mark.asyncio
    async def test_site_filter_narrows_the_query(self):
        coord = FederationCoordinator(make_registry())
        async with httpx.AsyncClient(transport=transport()) as client:
            result = await coord.query_property(
                "temperature", 50, site_ids=["zjnu_lab"], client=client
            )
        assert result.sites_queried == 1
        assert result.rows[0]["site_id"] == "zjnu_lab"

    @pytest.mark.asyncio
    async def test_empty_registry_returns_degraded_result(self):
        coord = FederationCoordinator(SiteRegistry())
        result = await coord.query_property("temperature", 50)
        assert result.sites_queried == 0
        assert result.degraded is True


class TestCompare:
    @pytest.mark.asyncio
    async def test_compare_summarises_each_site(self):
        coord = FederationCoordinator(make_registry())
        async with httpx.AsyncClient(transport=transport()) as client:
            summary = await coord.compare_property("temperature", 50, client=client)
        assert summary["sites_responded"] == 2
        assert len(summary["sites"]) == 2

    @pytest.mark.asyncio
    async def test_compare_reports_local_property_names(self):
        coord = FederationCoordinator(make_registry())
        async with httpx.AsyncClient(transport=transport()) as client:
            summary = await coord.compare_property("temperature", 50, client=client)
        partner = next(s for s in summary["sites"] if s["site_id"] == "partner_plant")
        assert partner["local_property"] == "airTemp"

    @pytest.mark.asyncio
    async def test_compare_computes_statistics(self):
        coord = FederationCoordinator(make_registry())
        async with httpx.AsyncClient(transport=transport()) as client:
            summary = await coord.compare_property("temperature", 50, client=client)
        partner = next(s for s in summary["sites"] if s["site_id"] == "partner_plant")
        assert partner["samples"] == 2
        assert partner["mean"] == pytest.approx(30.6, abs=0.1)

    @pytest.mark.asyncio
    async def test_compare_ranks_hottest_site_first(self):
        coord = FederationCoordinator(make_registry())
        async with httpx.AsyncClient(transport=transport()) as client:
            summary = await coord.compare_property("temperature", 50, client=client)
        assert summary["sites"][0]["site_id"] == "partner_plant"


class TestSeed:
    def test_seed_creates_two_sites_with_different_namespaces(self):
        seed_demo_sites("http://a/sparql", "http://b/sparql")
        assert len(site_registry) == 2
        namespaces = {s.ontology_namespace for s in site_registry.all()}
        assert len(namespaces) == 2

    def test_seeded_partner_has_alignment(self):
        seed_demo_sites("http://a/sparql", "http://b/sparql")
        partner = site_registry.get("partner_plant")
        assert partner is not None
        assert partner.localise("temperature") == "airTemp"
        assert partner.localise("co") == "carbonMonoxide"
