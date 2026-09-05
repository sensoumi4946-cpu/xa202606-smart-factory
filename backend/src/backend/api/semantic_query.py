

from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from backend import config
from semantic_layer.sparql_templates import (
    NAMED_QUERIES,
    cross_subsystem_correlation,
    latest_by_device,
    observations_in_window,
    provenance_trace,
)

router = APIRouter()

_TIMEOUT = 5.0


async def _run_query(sparql: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=_TIMEOUT, trust_env=False) as client:
        resp = await client.post(
            config.FUSEKI_QUERY_URL,
            content=sparql.encode("utf-8"),
            headers={
                "Content-Type": "application/sparql-query",
                "Accept": "application/sparql-results+json",
            },
        )
    resp.raise_for_status()
    return resp.json()["results"]["bindings"]


def _simplify(bindings: list[dict]) -> list[dict]:

    rows = []
    for b in bindings:
        row = {}
        for var, info in b.items():
            val = info.get("value", "")
            if "#" in val:
                val = val.rsplit("#", 1)[-1]
            row[var] = val
        rows.append(row)
    return rows


@router.get("/api/v1/semantic/device/{device_id}")
async def device_observations(
    device_id: str,
    limit: int = Query(10, ge=1, le=100),
):
    try:
        bindings = await _run_query(latest_by_device(device_id, limit))
    except httpx.HTTPError:
        return JSONResponse(
            status_code=503,
            content={"error": "semantic service unavailable"},
        )
    return {"device_id": device_id, "observations": _simplify(bindings)}


@router.get("/api/v1/semantic/window")
async def windowed_observations(
    minutes: int = Query(30, ge=1, le=1440),
):
    try:
        bindings = await _run_query(observations_in_window(minutes))
    except httpx.HTTPError:
        return JSONResponse(
            status_code=503,
            content={"error": "semantic service unavailable"},
        )
    return {"window_minutes": minutes, "observations": _simplify(bindings)}


@router.get("/api/v1/semantic/subsystems")
async def subsystem_overview():
    query_fn = NAMED_QUERIES["subsystem-summary"]
    try:
        bindings = await _run_query(query_fn())
    except httpx.HTTPError:
        return JSONResponse(
            status_code=503,
            content={"error": "semantic service unavailable"},
        )
    return {"subsystems": _simplify(bindings)}


@router.get("/api/v1/semantic/correlate")
async def correlate_properties(
    prop_a: str = Query(..., description="e.g. measuresTemperature"),
    prop_b: str = Query(..., description="e.g. measuresCO"),
    minutes: int = Query(10, ge=1, le=60),
):
    for p in (prop_a, prop_b):
        if not p.replace("_", "").isalnum():
            raise HTTPException(400, f"Invalid property name: {p}")

    try:
        q = cross_subsystem_correlation(prop_a, prop_b, minutes)
        bindings = await _run_query(q)
    except httpx.HTTPError:
        return JSONResponse(
            status_code=503,
            content={"error": "semantic service unavailable"},
        )
    return {
        "prop_a": prop_a,
        "prop_b": prop_b,
        "window_minutes": minutes,
        "pairs": _simplify(bindings),
    }


@router.get("/api/v1/semantic/provenance/{device_id}")
async def device_provenance(device_id: str):
    try:
        bindings = await _run_query(provenance_trace(device_id))
    except httpx.HTTPError:
        return JSONResponse(
            status_code=503,
            content={"error": "semantic service unavailable"},
        )
    return {"device_id": device_id, "provenance": _simplify(bindings)}
