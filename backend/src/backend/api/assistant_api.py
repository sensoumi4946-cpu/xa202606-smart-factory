from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from semantic_layer.meta_model import registry as meta_registry
from semantic_layer.nl_to_sparql import MAX_LIMIT, guard, translate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])

FALLBACK_PROPERTIES = [
    "temperature",
    "humidity",
    "co",
    "smoke",
    "combustible_gas",
    "distance",
    "count",
    "occupancy",
    "light_state",
]
FALLBACK_SUBSYSTEMS = ["temp_humidity", "lighting", "gas", "agv", "counting"]


def _vocabulary() -> tuple[list[str], list[str]]:
    properties = sorted(meta_registry.properties()) or FALLBACK_PROPERTIES
    subsystems = sorted(meta_registry.subsystems()) or FALLBACK_SUBSYSTEMS
    return properties, subsystems


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=400)
    execute: bool = True
    allow_llm: bool = True


@router.get("/vocabulary")
async def vocabulary() -> dict[str, Any]:
    properties, subsystems = _vocabulary()
    return {
        "properties": properties,
        "subsystems": subsystems,
        "ontology_version": meta_registry.version,
        "max_limit": MAX_LIMIT,
    }


@router.post("/translate")
async def translate_only(req: AskRequest) -> dict[str, Any]:
    properties, subsystems = _vocabulary()
    result = await translate(
        req.question, properties, subsystems, allow_llm=req.allow_llm
    )
    return result.to_dict()


@router.post("/ask")
async def ask(req: AskRequest) -> dict[str, Any]:
    properties, subsystems = _vocabulary()
    result = await translate(
        req.question, properties, subsystems, allow_llm=req.allow_llm
    )
    payload: dict[str, Any] = {**result.to_dict(), "rows": [], "executed": False}

    if not result.accepted:
        return payload

    if not req.execute:
        return payload

    try:
        from backend.api.semantic_query import _run_query, _simplify

        bindings = await _run_query(result.sparql)
        payload["rows"] = _simplify(bindings)
        payload["executed"] = True
    except Exception as exc:
        payload["violations"] = payload.get("violations", []) + [
            f"查询执行失败：{exc}"
        ]
    return payload


@router.post("/validate")
async def validate_sparql(sparql: str = Query(..., min_length=1)) -> dict[str, Any]:
    properties, subsystems = _vocabulary()
    ok, violations = guard(sparql, properties, subsystems)
    return {"accepted": ok, "violations": violations}
