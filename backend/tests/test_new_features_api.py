import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.store import init_db
from semantic_layer.meta_model import registry as meta_registry

VIBRATION = """
@prefix sf:   <http://example.org/smart-factory#> .
@prefix sosa: <http://www.w3.org/ns/sosa/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix unit: <http://qudt.org/vocab/unit/> .

sf:measuresVibration a sosa:ObservableProperty ;
    rdfs:label "vibration"@en, "振动"@zh ;
    sf:hasUnit unit:MilliM-PER-SEC ;
    sf:minValue "0.0"^^xsd:double ;
    sf:maxValue "50.0"^^xsd:double ;
    sf:warnThreshold "8.0"^^xsd:double ;
    sf:dangerThreshold "15.0"^^xsd:double ;
    sf:belongsToSubsystem sf:VibrationSubsystem .

sf:VibrationSubsystem a sf:Subsystem ;
    rdfs:label "vibration monitoring"@en, "振动监测"@zh .
"""

BROKEN = """
@prefix sf:   <http://example.org/smart-factory#> .
@prefix sosa: <http://www.w3.org/ns/sosa/> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

sf:measuresTorque a sosa:ObservableProperty ;
    sf:minValue "0.0"^^xsd:double ;
    sf:maxValue "100.0"^^xsd:double ;
    sf:belongsToSubsystem sf:DriveSubsystem .

sf:DriveSubsystem a sf:Subsystem .
"""


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    path = tmp_path / "api.db"
    monkeypatch.setattr("backend.store.DATABASE_PATH", str(path))
    monkeypatch.setattr("backend.config.DATABASE_PATH", str(path))
    init_db()
    meta_registry.reset()
    yield
    meta_registry.reset()


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestOntologyApi:
    @pytest.mark.asyncio
    async def test_load_accepts_valid_fragment(self):
        async with await _client() as c:
            resp = await c.post("/api/v1/semantic/ontology", json={"turtle": VIBRATION})
        assert resp.status_code == 201
        body = resp.json()
        assert body["accepted"] is True
        assert "vibration" in body["properties_added"]

    @pytest.mark.asyncio
    async def test_load_rejects_incomplete_fragment(self):
        async with await _client() as c:
            resp = await c.post("/api/v1/semantic/ontology", json={"turtle": BROKEN})
        assert resp.status_code == 422
        assert resp.json()["detail"]["accepted"] is False

    @pytest.mark.asyncio
    async def test_validate_does_not_mutate_the_registry(self):
        async with await _client() as c:
            await c.post("/api/v1/semantic/ontology/validate", json={"turtle": VIBRATION})
            props = await c.get("/api/v1/semantic/ontology/properties")
        assert props.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_version_changes_after_load(self):
        async with await _client() as c:
            before = (await c.get("/api/v1/semantic/ontology")).json()["version"]
            await c.post("/api/v1/semantic/ontology", json={"turtle": VIBRATION})
            after = (await c.get("/api/v1/semantic/ontology")).json()["version"]
        assert before != after

    @pytest.mark.asyncio
    async def test_dashboard_fields_appear_without_a_restart(self):
        async with await _client() as c:
            empty = await c.get("/api/v1/semantic/ontology/dashboard-fields")
            assert empty.json()["total"] == 0

            await c.post("/api/v1/semantic/ontology", json={"turtle": VIBRATION})

            filled = await c.get("/api/v1/semantic/ontology/dashboard-fields")
        items = filled.json()["items"]
        assert len(items) == 1
        assert items[0]["key"] == "vibration"
        assert items[0]["label"] == "振动"
        assert items[0]["danger"] == 15.0

    @pytest.mark.asyncio
    async def test_turtle_export_round_trips(self):
        async with await _client() as c:
            await c.post("/api/v1/semantic/ontology", json={"turtle": VIBRATION})
            resp = await c.get("/api/v1/semantic/ontology?format=turtle")
        assert "measuresVibration" in resp.text

    @pytest.mark.asyncio
    async def test_history_records_rejection(self):
        async with await _client() as c:
            await c.post("/api/v1/semantic/ontology", json={"turtle": BROKEN})
            resp = await c.get("/api/v1/semantic/ontology/history")
        assert resp.json()["items"][0]["accepted"] is False


class TestFederationApi:
    @pytest.mark.asyncio
    async def test_seed_registers_two_sites(self):
        async with await _client() as c:
            await c.post("/api/v1/federation/seed", json={})
            resp = await c.get("/api/v1/federation/sites")
        assert resp.json()["total"] == 2

    @pytest.mark.asyncio
    async def test_registered_sites_have_distinct_namespaces(self):
        async with await _client() as c:
            await c.post("/api/v1/federation/seed", json={})
            items = (await c.get("/api/v1/federation/sites")).json()["items"]
        assert len({i["ontology_namespace"] for i in items}) == 2

    @pytest.mark.asyncio
    async def test_partner_alignment_is_exposed(self):
        async with await _client() as c:
            await c.post("/api/v1/federation/seed", json={})
            items = (await c.get("/api/v1/federation/sites")).json()["items"]
        partner = next(i for i in items if i["site_id"] == "partner_plant")
        assert partner["alignment"]["airTemp"] == "temperature"

    @pytest.mark.asyncio
    async def test_register_custom_site(self):
        async with await _client() as c:
            resp = await c.post(
                "/api/v1/federation/sites",
                json={
                    "site_id": "plant_c",
                    "display_name": "第三工厂",
                    "sparql_endpoint": "http://c/sparql",
                },
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_removing_unknown_site_is_404(self):
        async with await _client() as c:
            resp = await c.delete("/api/v1/federation/sites/nope")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_query_with_unreachable_sites_degrades(self):
        async with await _client() as c:
            await c.post(
                "/api/v1/federation/seed",
                json={
                    "local_sparql": "http://127.0.0.1:59998/sparql",
                    "partner_sparql": "http://127.0.0.1:59999/sparql",
                },
            )
            resp = await c.get("/api/v1/federation/query?property=temperature")
        body = resp.json()
        assert body["sites_queried"] == 2
        assert body["sites_responded"] == 0
        assert body["degraded"] is True


class TestDecisionApi:
    @pytest.mark.asyncio
    async def test_empty_ledger(self):
        async with await _client() as c:
            await c.post("/api/v1/analytics/reset")
            resp = await c.get("/api/v1/decisions")
        assert resp.json()["items"] == []

    @pytest.mark.asyncio
    async def test_unknown_decision_is_404(self):
        async with await _client() as c:
            resp = await c.get("/api/v1/decisions/nope")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_hazard_produces_a_traceable_decision(self):
        async with await _client() as c:
            await c.post("/api/v1/analytics/reset")
            payload = {
                "schema_version": "v1",
                "device_id": "esp32_02_mq2",
                "subsystem": "gas",
                "protocol": "modbus",
                "measurements": [
                    {"type": "co", "value": 50.0, "unit": "ppm"},
                    {"type": "temperature", "value": 45.0, "unit": "celsius"},
                ],
            }
            await c.post("/ingest/api/v1/data", json=payload)
            resp = await c.get("/api/v1/decisions")

        items = resp.json()["items"]
        assert len(items) >= 1
        decision = items[0]
        assert decision["hazard_rule"] == "fire_risk"
        assert decision["target_device"] == "hvac_exhaust_01"
        assert decision["ontology_version"]
        assert decision["causal_chain"]
        assert "语义层" in decision["explanation_zh"]

    @pytest.mark.asyncio
    async def test_decision_verification_reports_chain_state(self):
        async with await _client() as c:
            await c.post("/api/v1/analytics/reset")
            payload = {
                "schema_version": "v1",
                "device_id": "esp32_02_mq2",
                "subsystem": "gas",
                "protocol": "modbus",
                "measurements": [
                    {"type": "co", "value": 50.0, "unit": "ppm"},
                    {"type": "temperature", "value": 45.0, "unit": "celsius"},
                ],
            }
            await c.post("/ingest/api/v1/data", json=payload)
            items = (await c.get("/api/v1/decisions")).json()["items"]
            resp = await c.get(f"/api/v1/decisions/{items[0]['decision_id']}/verify")

        body = resp.json()
        assert body["chain_valid"] is True
        assert body["fingerprint"]
