from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from analytics.thresholds import resolver
from semantic_layer.conformance_kit import render as render_kit
from semantic_layer.conformance_kit import run_kit, to_json as kit_json
from semantic_layer.meta_model import registry as meta_registry
from semantic_layer.ontology_migration import plan_migration
from semantic_layer.ontology_migration import render as render_plan
from semantic_layer.protocol_binding import (
    BindingRegistry,
    generate_all,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/innovation", tags=["innovation"])

binding_registry = BindingRegistry()


def load_bindings(path: Optional[str] = None) -> int:
    import os

    target = Path(path or os.getenv("BINDINGS_TTL", "bindings.ttl"))
    if not target.exists():
        logger.warning("bindings file %s not found", target)
        return 0
    result = binding_registry.load_turtle(target.read_text(encoding="utf-8"))
    if not result.accepted:
        logger.error("bindings rejected: %s", result.violations)
        return 0
    return len(binding_registry)


@router.get("/thresholds")
async def threshold_sources() -> dict[str, Any]:
    report = resolver.report()
    detail = []
    for name in resolver.known_properties():
        threshold = resolver.threshold_for(name)
        limit = resolver.limit_for(name)
        detail.append(
            {
                "property_name": name,
                "source": resolver.resolve_source(name),
                "danger": threshold[0] if threshold else None,
                "direction": threshold[1] if threshold else None,
                "warn": resolver.warn_for(name),
                "min": limit[0] if limit else None,
                "max": limit[1] if limit else None,
            }
        )
    return {**report, "properties": detail}


@router.get("/adapters")
async def generated_adapters() -> dict[str, Any]:
    if len(binding_registry) == 0:
        load_bindings()
    adapters = generate_all(binding_registry)
    return {
        "binding_count": len(binding_registry),
        "devices": binding_registry.devices(),
        "protocols": sorted(adapters),
        "generated_lines": {p: len(c.splitlines()) for p, c in adapters.items()},
        "hand_written_lines": 0,
    }


@router.get("/adapters/{protocol}")
async def adapter_source(protocol: str) -> dict[str, Any]:
    if len(binding_registry) == 0:
        load_bindings()
    adapters = generate_all(binding_registry)
    if protocol not in adapters:
        raise HTTPException(status_code=404, detail=f"no bindings for {protocol}")
    return {"protocol": protocol, "source": adapters[protocol]}


@router.get("/conformance/{device_id}")
async def conformance(
    device_id: str,
    subsystem: str = Query("temp_humidity"),
    protocol: str = Query("mqtt"),
    fmt: str = Query("json"),
) -> Any:
    properties = meta_registry.properties()
    if not properties:
        raise HTTPException(
            status_code=409, detail="no ontology loaded; POST a fragment first"
        )
    certificate = run_kit(
        device_id, subsystem, protocol, properties, meta_registry.version
    )
    if fmt == "text":
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse(render_kit(certificate))
    return certificate.to_dict()


class MigrationRequest(BaseModel):
    old_turtle: str = Field(..., min_length=1)
    new_turtle: str = Field(..., min_length=1)
    from_version: str = "v1"
    to_version: str = "v2"
    allow_breaking: bool = False


@router.post("/migration/plan")
async def migration_plan(req: MigrationRequest) -> dict[str, Any]:
    plan = plan_migration(
        req.old_turtle,
        req.new_turtle,
        req.from_version,
        req.to_version,
        req.allow_breaking,
    )
    return plan.to_dict()


@router.post("/migration/preview")
async def migration_preview(req: MigrationRequest) -> dict[str, str]:
    plan = plan_migration(
        req.old_turtle, req.new_turtle, req.from_version, req.to_version, True
    )
    return {"report": render_plan(plan)}
