from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 8.0

PREFIXES = """PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX sf:   <http://example.org/smart-factory#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX saref: <https://saref.etsi.org/core/>
"""


@dataclass
class FactorySite:
    site_id: str
    display_name: str
    sparql_endpoint: str
    ontology_namespace: str
    alignment: dict[str, str] = field(default_factory=dict)
    online: bool = True
    region: str = ""

    def canonical(self, local_property: str) -> str:
        return self.alignment.get(local_property, local_property)

    def localise(self, canonical_property: str) -> str:
        for local, canon in self.alignment.items():
            if canon == canonical_property:
                return local
        return canonical_property


@dataclass
class SiteResult:
    site_id: str
    display_name: str
    ok: bool
    rows: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "display_name": self.display_name,
            "ok": self.ok,
            "row_count": len(self.rows),
            "rows": self.rows,
            "latency_ms": round(self.latency_ms, 1),
            "error": self.error,
        }


@dataclass
class FederatedResult:
    query_id: str
    canonical_property: str
    sites_queried: int
    sites_responded: int
    total_rows: int
    rows: list[dict[str, Any]]
    per_site: list[dict[str, Any]]
    elapsed_ms: float
    degraded: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "canonical_property": self.canonical_property,
            "sites_queried": self.sites_queried,
            "sites_responded": self.sites_responded,
            "total_rows": self.total_rows,
            "rows": self.rows,
            "per_site": self.per_site,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "degraded": self.degraded,
        }


class SiteRegistry:
    def __init__(self) -> None:
        self._sites: dict[str, FactorySite] = {}

    def register(self, site: FactorySite) -> None:
        self._sites[site.site_id] = site
        logger.info(
            "site registered: %s (%s) ns=%s",
            site.site_id,
            site.sparql_endpoint,
            site.ontology_namespace,
        )

    def unregister(self, site_id: str) -> None:
        self._sites.pop(site_id, None)

    def get(self, site_id: str) -> Optional[FactorySite]:
        return self._sites.get(site_id)

    def all(self) -> list[FactorySite]:
        return list(self._sites.values())

    def online(self) -> list[FactorySite]:
        return [s for s in self._sites.values() if s.online]

    def set_online(self, site_id: str, online: bool) -> None:
        site = self._sites.get(site_id)
        if site is not None:
            site.online = online

    def reset(self) -> None:
        self._sites.clear()

    def __len__(self) -> int:
        return len(self._sites)


def build_property_query(local_property: str, limit: int = 50) -> str:
    safe_property = "".join(
        ch for ch in local_property if ch.isalnum() or ch in ("_", "-")
    )
    safe_limit = max(1, min(int(limit), 1000))
    return (
        PREFIXES
        + "SELECT ?sensor ?value ?time WHERE {\n"
        "  ?obs a sosa:Observation ;\n"
        "       sosa:madeBySensor ?sensor ;\n"
        "       sosa:observedProperty ?prop ;\n"
        "       sosa:hasSimpleResult ?value ;\n"
        "       sosa:resultTime ?time .\n"
        f'  FILTER(CONTAINS(LCASE(STR(?prop)), "{safe_property.lower()}"))\n'
        "}\n"
        f"ORDER BY DESC(?time) LIMIT {safe_limit}"
    )


def _parse_bindings(payload: dict) -> list[dict[str, Any]]:
    rows = []
    for binding in payload.get("results", {}).get("bindings", []):
        row = {}
        for key, cell in binding.items():
            value = cell.get("value")
            datatype = cell.get("datatype", "")
            if datatype.endswith(("double", "float", "decimal", "integer", "int")):
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    pass
            row[key] = value
        rows.append(row)
    return rows


async def query_site(
    site: FactorySite,
    canonical_property: str,
    limit: int,
    client: httpx.AsyncClient,
    timeout: float = DEFAULT_TIMEOUT,
) -> SiteResult:
    local_property = site.localise(canonical_property)
    sparql = build_property_query(local_property, limit)
    start = time.perf_counter()

    try:
        response = await client.post(
            site.sparql_endpoint,
            data={"query": sparql},
            headers={"Accept": "application/sparql-results+json"},
            timeout=timeout,
        )
        elapsed = (time.perf_counter() - start) * 1000.0

        if response.status_code != 200:
            return SiteResult(
                site_id=site.site_id,
                display_name=site.display_name,
                ok=False,
                latency_ms=elapsed,
                error=f"HTTP {response.status_code}",
            )

        rows = _parse_bindings(response.json())
        for row in rows:
            row["site_id"] = site.site_id
            row["site_name"] = site.display_name
            row["local_property"] = local_property
            row["canonical_property"] = canonical_property

        return SiteResult(
            site_id=site.site_id,
            display_name=site.display_name,
            ok=True,
            rows=rows,
            latency_ms=elapsed,
        )
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000.0
        return SiteResult(
            site_id=site.site_id,
            display_name=site.display_name,
            ok=False,
            latency_ms=elapsed,
            error=str(exc)[:160],
        )


class FederationCoordinator:
    def __init__(
        self,
        registry: Optional[SiteRegistry] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.registry = registry if registry is not None else SiteRegistry()
        self.timeout = timeout
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"fq-{self._counter:04d}"

    async def query_property(
        self,
        canonical_property: str,
        limit: int = 50,
        site_ids: Optional[list[str]] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> FederatedResult:
        sites = self.registry.online()
        if site_ids:
            wanted = set(site_ids)
            sites = [s for s in sites if s.site_id in wanted]

        query_id = self._next_id()
        start = time.perf_counter()

        if not sites:
            return FederatedResult(
                query_id=query_id,
                canonical_property=canonical_property,
                sites_queried=0,
                sites_responded=0,
                total_rows=0,
                rows=[],
                per_site=[],
                elapsed_ms=0.0,
                degraded=True,
            )

        owns_client = client is None
        client = client or httpx.AsyncClient()
        try:
            results = await asyncio.gather(
                *(
                    query_site(site, canonical_property, limit, client, self.timeout)
                    for site in sites
                )
            )
        finally:
            if owns_client:
                await client.aclose()

        elapsed = (time.perf_counter() - start) * 1000.0
        merged: list[dict[str, Any]] = []
        for result in results:
            merged.extend(result.rows)
        merged.sort(key=lambda r: str(r.get("time", "")), reverse=True)

        responded = sum(1 for r in results if r.ok)
        return FederatedResult(
            query_id=query_id,
            canonical_property=canonical_property,
            sites_queried=len(sites),
            sites_responded=responded,
            total_rows=len(merged),
            rows=merged[:limit],
            per_site=[r.to_dict() for r in results],
            elapsed_ms=elapsed,
            degraded=responded < len(sites),
        )

    async def compare_property(
        self,
        canonical_property: str,
        limit: int = 50,
        client: Optional[httpx.AsyncClient] = None,
    ) -> dict[str, Any]:
        result = await self.query_property(canonical_property, limit, client=client)

        by_site: dict[str, list[float]] = {}
        for row in result.rows:
            value = row.get("value")
            if isinstance(value, (int, float)):
                by_site.setdefault(str(row.get("site_id")), []).append(float(value))

        summary = []
        for site_id, values in by_site.items():
            site = self.registry.get(site_id)
            summary.append(
                {
                    "site_id": site_id,
                    "display_name": site.display_name if site else site_id,
                    "local_property": site.localise(canonical_property)
                    if site
                    else canonical_property,
                    "samples": len(values),
                    "min": round(min(values), 2),
                    "max": round(max(values), 2),
                    "mean": round(sum(values) / len(values), 2),
                }
            )
        summary.sort(key=lambda s: s["mean"], reverse=True)

        return {
            "canonical_property": canonical_property,
            "sites": summary,
            "sites_queried": result.sites_queried,
            "sites_responded": result.sites_responded,
            "degraded": result.degraded,
            "elapsed_ms": round(result.elapsed_ms, 1),
        }


site_registry = SiteRegistry()
coordinator = FederationCoordinator(site_registry)


def seed_demo_sites(local_sparql: str, partner_sparql: str) -> None:
    site_registry.reset()
    site_registry.register(
        FactorySite(
            site_id="zjnu_lab",
            display_name="金华智造实验工厂",
            sparql_endpoint=local_sparql,
            ontology_namespace="http://example.org/smart-factory#",
            alignment={},
            region="浙江金华",
        )
    )
    site_registry.register(
        FactorySite(
            site_id="partner_plant",
            display_name="合作方装配车间",
            sparql_endpoint=partner_sparql,
            ontology_namespace="http://partner.example.org/plant#",
            alignment={
                "airTemp": "temperature",
                "relHumidity": "humidity",
                "carbonMonoxide": "co",
                "proximity": "distance",
                "unitCount": "count",
            },
            region="江苏南京",
        )
    )
