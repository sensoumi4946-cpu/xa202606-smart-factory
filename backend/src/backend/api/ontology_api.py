from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from semantic_layer.meta_model import registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/semantic", tags=["semantic"])


class OntologyFragment(BaseModel):
    turtle: str = Field(..., min_length=1)
    note: Optional[str] = None


@router.post("/ontology", status_code=status.HTTP_201_CREATED)
async def load_ontology(fragment: OntologyFragment) -> dict[str, Any]:
    result = registry.load_turtle(fragment.turtle)
    if not result.accepted:
        raise HTTPException(status_code=422, detail=result.to_dict())
    return result.to_dict()


@router.post("/ontology/validate")
async def validate_ontology(fragment: OntologyFragment) -> dict[str, Any]:
    from semantic_layer.meta_model import validate_fragment

    accepted, violations, graph = validate_fragment(fragment.turtle)
    return {
        "accepted": accepted,
        "violations": violations,
        "triples": len(graph),
    }


@router.get("/ontology")
async def current_ontology(format: str = Query("json")) -> Any:
    if format == "turtle":
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse(
            registry.serialize("turtle"), media_type="text/turtle"
        )
    return {
        "version": registry.version,
        "properties": [d.to_dict() for d in registry.properties().values()],
        "subsystems": registry.subsystems(),
    }


@router.get("/ontology/properties")
async def properties() -> dict[str, Any]:
    props = registry.properties()
    return {"items": [d.to_dict() for d in props.values()], "total": len(props)}


@router.get("/ontology/dashboard-fields")
async def dashboard_fields() -> dict[str, Any]:
    fields = registry.dashboard_fields()
    return {"version": registry.version, "items": fields, "total": len(fields)}


@router.get("/ontology/history")
async def history(limit: int = Query(20, ge=1, le=50)) -> dict[str, Any]:
    return {"items": registry.history(limit)}


@router.post("/ontology/reset")
async def reset() -> dict[str, str]:
    registry.reset()
    return {"status": "reset", "version": registry.version}
