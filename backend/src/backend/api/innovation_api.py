from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from analytics.thresholds import resolver
from semantic_layer.conformance_kit import render as render_kit
from semantic_layer.conformance_kit import run_kit
from semantic_layer.meta_model import registry as meta_registry
from semantic_layer.ontology_migration import plan_migration
from semantic_layer.ontology_migration import render as render_plan
from semantic_layer.protocol_binding import BindingRegistry, generate_all

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/innovation", tags=["innovation"])

binding_registry = BindingRegistry()

HAND_WRITTEN_ADAPTER_FILES = (
    "connectivity/src/connectivity/adapters/mqtt_adapter.py",
    "connectivity/src/connectivity/adapters/modbus_adapter.py",
    "connectivity/src/connectivity/adapters/opcua_adapter.py",
    "connectivity/src/connectivity/adapters/rest_adapter.py",
)

BINDING_CONSTANT_MARKERS = (
    "REGISTER_BASE",
    "REGISTER_COUNT",
    "40001",
    "register_map",
    "node_map",
    "topic_map",
)


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "bindings.ttl").exists():
            return parent
    return Path.cwd()


def _candidate_paths(name: str) -> list[Path]:
    here = Path(__file__).resolve()
    roots = [Path.cwd(), *here.parents[:6]]
    seen: set[Path] = set()
    out: list[Path] = []
    for root in roots:
        candidate = (root / name).resolve()
        if candidate not in seen:
            seen.add(candidate)
            out.append(candidate)
    return out


def load_bindings(path: Optional[str] = None) -> int:
    name = path or os.getenv("BINDINGS_TTL", "bindings.ttl")
    target = Path(name)
    if not target.is_absolute() or not target.exists():
        for candidate in _candidate_paths(name):
            if candidate.exists():
                target = candidate
                break
    if not target.exists():
        logger.warning(
            "bindings file %s not found (searched %s) — adapter generation DISABLED",
            name,
            [str(p) for p in _candidate_paths(name)[:4]],
        )
        return 0
    result = binding_registry.load_turtle(target.read_text(encoding="utf-8"))
    if not result.accepted:
        logger.error("bindings rejected: %s", result.violations)
        return 0
    return len(binding_registry)


def adapter_line_audit() -> dict[str, Any]:
    root = _repo_root()
    total = 0
    hardcoded: list[str] = []
    for relative in HAND_WRITTEN_ADAPTER_FILES:
        path = root / relative
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        total += len(lines)
        for number, line in enumerate(lines, start=1):
            if any(marker in line for marker in BINDING_CONSTANT_MARKERS):
                hardcoded.append(f"{relative}:{number}")
    return {
        "transport_plumbing_lines": total,
        "hardcoded_binding_constants": hardcoded,
        "single_source_of_truth": not hardcoded,
    }


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
        "device_aliases": binding_registry.aliases(),
        "protocols": sorted(adapters),
        "generated_lines": {p: len(c.splitlines()) for p, c in adapters.items()},
        "generated_lines_total": sum(len(c.splitlines()) for c in adapters.values()),
        **adapter_line_audit(),
    }


@router.get("/bindings")
async def declared_bindings() -> dict[str, Any]:
    if len(binding_registry) == 0:
        load_bindings()
    return {
        "binding_count": len(binding_registry),
        "bindings": [b.to_dict() for b in binding_registry.all()],
    }


@router.get("/bindings/{device_id}/triples")
async def device_triples(device_id: str) -> dict[str, Any]:
    if len(binding_registry) == 0:
        load_bindings()
    canonical = binding_registry.resolve_device_id(device_id)
    bindings = binding_registry.for_device(canonical)
    if not bindings:
        raise HTTPException(status_code=404, detail=f"no bindings for {device_id}")
    return {
        "reported_device_id": device_id,
        "device_id": canonical,
        "triples": [
            {
                "subject": f"sf:{b.binding_id}",
                "predicates": {
                    key: value
                    for key, value in b.to_dict().items()
                    if key != "binding_id" and value not in (None, "", [])
                },
            }
            for b in bindings
        ],
    }


@router.get("/adapters/{protocol}")
async def adapter_source(protocol: str) -> dict[str, Any]:
    if len(binding_registry) == 0:
        load_bindings()
    adapters = generate_all(binding_registry)
    if protocol not in adapters:
        declared = sorted({b.protocol for b in binding_registry.all()})
        if protocol in declared:
            raise HTTPException(
                status_code=501,
                detail=f"bindings declared for {protocol} but no generator implemented",
            )
        raise HTTPException(
            status_code=404,
            detail=f"no bindings declared for {protocol}; declared: {declared}",
        )
    return {"protocol": protocol, "source": adapters[protocol]}


class ValidateRequest(BaseModel):
    turtle: str = Field(..., min_length=1)


@router.post("/validate")
async def validate_turtle(payload: ValidateRequest) -> dict[str, Any]:
    scratch = BindingRegistry()
    result = scratch.load_turtle(payload.turtle)
    if not result.accepted:
        return {
            "accepted": False,
            "violations": result.violations,
            "bindings_added": [],
            "devices": [],
            "generated_source": "",
        }
    adapters = generate_all(scratch)
    return {
        "accepted": True,
        "violations": [],
        "bindings_added": result.bindings_added,
        "devices": scratch.devices(),
        "generated_source": "\n\n".join(adapters.values()),
    }


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