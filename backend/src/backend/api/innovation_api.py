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
from rdflib import Literal

from semantic_layer.protocol_binding import (
    GENERATORS,
    SF,
    BindingRegistry,
    generate_all,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/innovation", tags=["innovation"])

binding_registry = BindingRegistry()

BINDINGS_FILENAME = "bindings.ttl"

ADAPTER_FILES = (
    "modbus_adapter.py",
    "mqtt_adapter.py",
    "opcua_adapter.py",
    "rest_adapter.py",
)

BINDING_CONSTANTS = (
    "REGISTER_BASE",
    "REGISTER_COUNT",
    "REGISTER_MAP",
    "SENSOR_TOPIC",
    "TOPIC_MAP",
    "NODE_MAP",
    "ROUTE_MAP",
    "LIGHTING_MAP",
    "MODBUS_DEVICE_ID",
    "OPCUA_DEVICE_ID",
    "OPCUA_DISTANCE_NODE_ID",
    "read_holding_registers",
    "read_input_registers",
)


def find_bindings_file(start: Optional[str] = None) -> Optional[Path]:
    import os

    override = os.getenv("BINDINGS_TTL")
    if override:
        candidate = Path(override).expanduser()
        return candidate if candidate.is_file() else None

    origin = Path(start or __file__).resolve()
    for parent in (origin, *origin.parents):
        candidate = parent / BINDINGS_FILENAME
        if candidate.is_file():
            return candidate
    return None


def load_bindings(path: Optional[str] = None) -> int:
    target = Path(path) if path else find_bindings_file()
    if target is None or not target.is_file():
        logger.warning("bindings file %s not found", target or BINDINGS_FILENAME)
        return 0
    result = binding_registry.load_turtle(target.read_text(encoding="utf-8"))
    if not result.accepted:
        logger.error("bindings rejected: %s", result.violations)
        return 0
    return len(binding_registry)


def _adapter_dir() -> Optional[Path]:
    origin = Path(__file__).resolve()
    for parent in origin.parents:
        candidate = parent / "connectivity" / "src" / "connectivity" / "adapters"
        if candidate.is_dir():
            return candidate
    return None


def adapter_line_audit() -> dict[str, Any]:
    directory = _adapter_dir()
    files: list[dict[str, Any]] = []
    total_lines = 0
    total_binding_lines = 0

    for name in ADAPTER_FILES:
        entry: dict[str, Any] = {
            "file": name,
            "found": False,
            "total_lines": 0,
            "binding_lines": 0,
            "constants": [],
            "hits": [],
        }
        path = directory / name if directory else None
        if path is not None and path.is_file():
            entry["found"] = True
            lines = path.read_text(encoding="utf-8").splitlines()
            entry["total_lines"] = len(lines)
            hits = []
            constants = set()
            for number, line in enumerate(lines, start=1):
                matched = [c for c in BINDING_CONSTANTS if c in line]
                if not matched:
                    continue
                constants.update(matched)
                hits.append(
                    {
                        "line": number,
                        "constants": sorted(matched),
                        "text": line.strip(),
                    }
                )
            entry["binding_lines"] = len(hits)
            entry["constants"] = sorted(constants)
            entry["hits"] = hits
            total_lines += entry["total_lines"]
            total_binding_lines += entry["binding_lines"]
        files.append(entry)

    return {
        "adapter_dir": str(directory) if directory else None,
        "files": files,
        "total_lines": total_lines,
        "hand_written_binding_lines": total_binding_lines,
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
    audit = adapter_line_audit()
    return {
        "binding_count": len(binding_registry),
        "devices": binding_registry.devices(),
        "aliases": binding_registry.aliases(),
        "protocols": sorted(adapters),
        "generated_lines": {p: len(c.splitlines()) for p, c in adapters.items()},
        "hand_written_lines": audit["hand_written_binding_lines"],
        "adapter_audit": audit,
    }


@router.get("/adapters/audit")
async def adapter_audit() -> dict[str, Any]:
    return adapter_line_audit()


@router.get("/bindings")
async def bindings() -> dict[str, Any]:
    if len(binding_registry) == 0:
        load_bindings()
    return {
        "binding_count": len(binding_registry),
        "devices": binding_registry.devices(),
        "aliases": binding_registry.aliases(),
        "bindings": [b.to_dict() for b in binding_registry.all()],
    }


@router.get("/bindings/{device_id}/triples")
async def binding_triples(device_id: str) -> dict[str, Any]:
    if len(binding_registry) == 0:
        load_bindings()

    resolved = binding_registry.resolve_device_id(device_id)
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"no bindings for {device_id}")

    matched = binding_registry.for_device(resolved)
    graph = binding_registry.graph()
    subjects = set(graph.subjects(SF.deviceId, Literal(resolved)))

    triples = [
        {"subject": str(s), "predicate": str(p), "object": str(o)}
        for s, p, o in graph
        if s in subjects
    ]
    triples.sort(key=lambda t: (t["subject"], t["predicate"], t["object"]))

    return {
        "device_id": resolved,
        "requested_device_id": device_id,
        "binding_count": len(matched),
        "bindings": [b.to_dict() for b in matched],
        "triple_count": len(triples),
        "triples": triples,
    }


@router.get("/adapters/{protocol}")
async def adapter_source(protocol: str) -> dict[str, Any]:
    if len(binding_registry) == 0:
        load_bindings()
    adapters = generate_all(binding_registry)
    if protocol in adapters:
        return {"protocol": protocol, "source": adapters[protocol]}
    if binding_registry.for_protocol(protocol) and protocol not in GENERATORS:
        raise HTTPException(
            status_code=501,
            detail=f"bindings exist for {protocol} but no generator is implemented",
        )
    raise HTTPException(status_code=404, detail=f"no bindings for {protocol}")


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
