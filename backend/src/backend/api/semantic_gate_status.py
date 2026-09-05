import httpx
from fastapi import APIRouter, HTTPException

from backend import config
from backend.services import gate_status_tracker

router = APIRouter()


@router.get("/api/v1/semantic/gate-status")
async def gate_status():
    snap = gate_status_tracker.snapshot()
    if snap["status"] is None:
        return {
            **snap,
            "status": "waiting",
            "reason": "no ingest activity yet",
        }
    return snap


@router.post("/api/v1/semantic/query")
async def semantic_query(body: dict):
    query = body.get("query")
    if not query:
        raise HTTPException(status_code=422, detail="missing 'query' field")

    try:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            resp = await client.post(
                config.FUSEKI_QUERY_URL,
                data={"query": query},
                headers={"Accept": "application/sparql-results+json"},
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="semantic service unavailable")
