from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
import httpx
from backend import config
from semantic_layer.sparql_federated_query import NodeRegistry, execute_federated

router = APIRouter()
_node_registry = NodeRegistry()

# Populate registry from FEDERATED_NODES env var on import
if config.FEDERATED_NODES:
    from semantic_layer.sparql_federated_query import FactoryNode
    for i, url in enumerate(config.FEDERATED_NODES.split(",")):
        url = url.strip()
        if url:
            _node_registry.register(FactoryNode(
                node_id=f"node_{i}",
                sparql_endpoint=url,
                data_endpoint=url.replace("/sparql", "/data"),
            ))

@router.get("/api/v1/semantic/federated")
async def federated_query(sparql: str = Query(..., description="SPARQL SELECT query")):
    if not _node_registry.online_nodes():
        return JSONResponse(
            status_code=503,
            content={"error": "No federated nodes configured (set FEDERATED_NODES env var)"},
        )
    result = await execute_federated(_node_registry, sparql)
    return result