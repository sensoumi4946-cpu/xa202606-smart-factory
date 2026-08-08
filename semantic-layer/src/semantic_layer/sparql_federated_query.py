# Federated SPARQL for distributed HCPS knowledge graphs


from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 8.0

@dataclass
class FactoryNode:
    """One C⁶ node in the distributed manufacturing OS."""
    node_id: str               
    sparql_endpoint: str       
    data_endpoint: str         
    role: str = "assistant"    
    online: bool = True

    @property
    def service_uri(self) -> str:
        return self.sparql_endpoint


class NodeRegistry:

    def __init__(self) -> None:
        self._nodes: dict[str, FactoryNode] = {}

    def register(self, node: FactoryNode) -> None:
        self._nodes[node.node_id] = node
        logger.info("Node registered: %s (%s) → %s", node.node_id, node.role, node.sparql_endpoint)

    def unregister(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)

    def mark_offline(self, node_id: str) -> None:
        if node_id in self._nodes:
            self._nodes[node_id].online = False

    def online_nodes(self) -> list[FactoryNode]:
        return [n for n in self._nodes.values() if n.online]

    def all_nodes(self) -> list[FactoryNode]:
        return list(self._nodes.values())

    def get(self, node_id: str) -> Optional[FactoryNode]:
        return self._nodes.get(node_id)

    def __len__(self) -> int:
        return len(self._nodes)

_PREFIXES = """\
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX sf:   <http://example.org/smart-factory#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
PREFIX prov: <http://www.w3.org/ns/prov#>
"""


def build_service_query(
    inner_pattern: str,
    select_vars: str,
    nodes: list[FactoryNode],
    distinct: bool = True,
) -> str:
    
    if not nodes:
        raise ValueError("No nodes provided for federation")

    blocks = []
    for node in nodes:
        blocks.append(
            f"  {{ SERVICE <{node.service_uri}> {{\n"
            f"    {inner_pattern}\n"
            f"  }} }}"
        )

    union_body = "\n  UNION\n".join(blocks)
    distinct_kw = "DISTINCT " if distinct else ""

    return (
        _PREFIXES
        + f"\nSELECT {distinct_kw}{select_vars} WHERE {{\n"
        + union_body
        + "\n}"
    )


def federated_latest_all_nodes(nodes: list[FactoryNode], limit: int = 50) -> str:
    
    inner = (
        "?obs a sosa:Observation ;\n"
        "     sosa:madeBySensor ?sensor ;\n"
        "     sosa:observedProperty ?prop ;\n"
        "     sosa:hasSimpleResult ?value ;\n"
        "     sosa:resultTime ?time .\n"
        "OPTIONAL { ?sensor sf:belongsToSubsystem ?subsystem }"
    )
    q = build_service_query(inner, "?sensor ?prop ?value ?time ?subsystem", nodes)
    return q + f"\nORDER BY DESC(?time) LIMIT {limit}"


def federated_fire_risk(nodes: list[FactoryNode]) -> str:
    
    inner = (
        "?t a sosa:Observation ;\n"
        "   sosa:madeBySensor ?tempSensor ;\n"
        "   sosa:observedProperty sf:measuresTemperature ;\n"
        "   sosa:hasSimpleResult ?tempVal .\n"
        "?g a sosa:Observation ;\n"
        "   sosa:madeBySensor ?gasSensor ;\n"
        "   sosa:observedProperty ?gasProp ;\n"
        "   sosa:hasSimpleResult ?gasVal .\n"
        "VALUES ?gasProp { sf:measuresCO sf:measuresSmoke sf:measuresCombustibleGas }\n"
        "FILTER(?tempVal > 35)\n"
        "FILTER(?gasVal  > 30)"
    )
    return build_service_query(
        inner,
        "?tempSensor ?tempVal ?gasSensor ?gasVal",
        nodes,
    )



@dataclass
class NodeResult:
    node_id: str
    bindings: list[dict[str, Any]]
    latency_ms: float
    error: Optional[str] = None


async def _query_node(
    node: FactoryNode,
    sparql: str,
    client: httpx.AsyncClient,
) -> NodeResult:
    t0 = time.perf_counter()
    try:
        resp = await client.post(
            node.sparql_endpoint,
            content=sparql.encode("utf-8"),
            headers={
                "Content-Type": "application/sparql-query",
                "Accept": "application/sparql-results+json",
            },
        )
        resp.raise_for_status()
        bindings = resp.json()["results"]["bindings"]
        return NodeResult(
            node_id=node.node_id,
            bindings=bindings,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
    except httpx.HTTPError as exc:
        logger.warning("Node %s query failed: %s", node.node_id, exc)
        return NodeResult(
            node_id=node.node_id,
            bindings=[],
            latency_ms=(time.perf_counter() - t0) * 1000,
            error=str(exc),
        )


async def execute_federated(
    registry: NodeRegistry,
    sparql: str,
    timeout: float = _TIMEOUT,
) -> dict[str, Any]:

    nodes = registry.online_nodes()
    if not nodes:
        return {"nodes_queried": 0, "nodes_ok": 0, "nodes_error": 0,
                "total_bindings": 0, "results": [], "node_latencies": {}}

    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = [_query_node(n, sparql, client) for n in nodes]
        node_results: list[NodeResult] = await asyncio.gather(*tasks)

    merged: list[dict] = []
    latencies: dict[str, float] = {}
    errors = 0

    for nr in node_results:
        latencies[nr.node_id] = round(nr.latency_ms, 2)
        if nr.error:
            errors += 1
        else:
            for b in nr.bindings:
                b["_node"] = {"type": "literal", "value": nr.node_id}
            merged.extend(nr.bindings)

    return {
        "nodes_queried": len(nodes),
        "nodes_ok": len(nodes) - errors,
        "nodes_error": errors,
        "total_bindings": len(merged),
        "results": merged,
        "node_latencies": latencies,
    }
