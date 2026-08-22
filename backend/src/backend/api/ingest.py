# receives UnifiedMessage from connectivity adapters
# runs semantic gate, writes to SQLite and Fuseki.

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend import config
from backend.services.registry_singleton import aas_registry, provenance_audit
from backend.services import gate_status_tracker
from backend.services.analytics_ingest_bridge import analyse_after_ingest
from semantic_layer.fuseki import write_to_fuseki
from semantic_layer.observation_gate import check_and_prepare
from semantic_layer.semantic_context_rules import evaluate_with_context
from semantic_layer.aas_live_sync import LiveDevice, register_device_in_fuseki
from smart_factory_contracts.messages import (
    Measurement, MeasurementType, Protocol, Subsystem, Unit, UnifiedMessage,
)
from backend.store import insert_sensor_data
from backend.api.prediction import process_reading as run_prediction_pipeline
from semantic_layer.mapping import TYPE_TO_PROPERTY

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingest"])

_MTYPE = {m.value: m for m in MeasurementType}
_UNIT  = {u.value: u for u in Unit}
_PROTO = {p.value: p for p in Protocol}
_SUB   = {s.value: s for s in Subsystem}

_PROPERTY_BY_TYPE = {
    mtype.value: str(uri).rsplit("#", 1)[-1] for mtype, uri in TYPE_TO_PROPERTY.items()
}


def _observable_property(property_name: str) -> str:
    key = str(property_name or "").strip()
    known = _PROPERTY_BY_TYPE.get(key.lower())
    if known:
        return known
    parts = [p for p in key.replace("-", "_").split("_") if p]
    if not parts:
        return "measures"
    return "measures" + "".join(p[:1].upper() + p[1:] for p in parts)


def _canonical_device_id(device_id: str) -> str:
    raw = str(device_id or "")
    try:
        from backend.api.innovation_api import binding_registry, load_bindings

        if len(binding_registry) == 0:
            load_bindings()
        resolved = binding_registry.resolve_device_id(raw)
    except Exception as exc:
        logger.debug("device id resolution unavailable for %s: %s", raw, exc)
        return raw
    return resolved or raw


class SensorReading(BaseModel):
    sensor_id: str
    subsystem: str
    protocol: str
    property_name: str
    value: float
    unit: str
    timestamp: str


def _to_unified(reading: SensorReading) -> UnifiedMessage:
    mtype  = _MTYPE.get(reading.property_name.lower())
    unit   = _UNIT.get(reading.unit.lower())
    proto  = _PROTO.get(reading.protocol.lower())
    sub    = _SUB.get(reading.subsystem.lower())

    if mtype is None:
        raise ValueError(f"Unknown property_name '{reading.property_name}'. Valid: {list(_MTYPE)}")
    if unit is None:
        raise ValueError(f"Unknown unit '{reading.unit}'. Valid: {list(_UNIT)}")
    if proto is None:
        raise ValueError(f"Unknown protocol '{reading.protocol}'. Valid: {list(_PROTO)}")
    if sub is None:
        raise ValueError(f"Unknown subsystem '{reading.subsystem}'. Valid: {list(_SUB)}")

    return UnifiedMessage(
        schema_version="v1",
        device_id=_canonical_device_id(reading.sensor_id),
        subsystem=sub,
        protocol=proto,
        timestamp=datetime.now(timezone.utc),
        measurements=[Measurement(type=mtype, value=reading.value, unit=unit)],
    )


@router.post("/reading")
async def ingest_reading(
    reading: SensorReading,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    ingest_id = str(uuid.uuid4())

    try:
        msg = _to_unified(reading)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # SHACL + QUDT + provenance
    gate = check_and_prepare(msg)
    if not gate.accepted:
        provenance_audit.record_attempt(
            ingest_id=ingest_id,
            device_id=reading.sensor_id,
            protocol=reading.protocol,
            observation_timestamp=datetime.now(timezone.utc),
            kg_written=False,
            error="SHACL gate rejected: " + "; ".join(gate.report.violations),
        )
        raise HTTPException(
            status_code=422,
            detail={"error": "Semantic validation failed", "violations": gate.report.violations},
        )

    record_id = insert_sensor_data(msg)

    fired_alerts = analyse_after_ingest(
        device_id=reading.sensor_id,
        subsystem=reading.subsystem,
        protocol=reading.protocol,
        measurements=[{"type": reading.property_name, "value": reading.value, "unit": reading.unit}],
    )

    ctx_alerts = []
    if gate.graph is not None:
        ctx_alerts = evaluate_with_context(
            device_id=reading.sensor_id,
            observable_property=_observable_property(reading.property_name),
            value=reading.value,
            graph=gate.graph,
        )
        for a in ctx_alerts:
            logger.warning("Context alert: %s", a.message)

    device = LiveDevice(
        device_id=reading.sensor_id,
        subsystem=reading.subsystem,
        protocol=reading.protocol.lower(),
        measurement_types=[reading.property_name],
    )
    if aas_registry.observe(device):
        background_tasks.add_task(register_device_in_fuseki, device, config.FUSEKI_ENDPOINT)
        
    kg_written = await write_to_fuseki(msg, config.FUSEKI_ENDPOINT)
    provenance_audit.record_attempt(
        ingest_id=ingest_id,
        device_id=reading.sensor_id,
        protocol=reading.protocol,
        observation_timestamp=datetime.now(timezone.utc),
        kg_written=kg_written,
        error=None if kg_written else "Fuseki unreachable",
    )

    return {
        "status": "ok",
        "record_id": record_id,
        "ingest_id": ingest_id,
        "kg_written": kg_written,
        "anomaly_alerts": len(fired_alerts),
        "semantic_alerts": len(ctx_alerts),
    }


@router.post("/batch")
async def ingest_batch(
    readings: list[SensorReading],
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    accepted, rejected = [], []
    for r in readings:
        try:
            result = await ingest_reading(r, background_tasks)
            accepted.append(r.sensor_id)
        except HTTPException as exc:
            rejected.append({"sensor_id": r.sensor_id, "reason": str(exc.detail)})
    return {
        "total": len(readings),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "rejected_detail": rejected,
    }

@router.post("/api/v1/data")
async def ingest_unified_data(
    msg: UnifiedMessage,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    ingest_id = str(uuid.uuid4())
    canonical_id = _canonical_device_id(msg.device_id)
    if canonical_id != msg.device_id:
        msg = msg.model_copy(update={"device_id": canonical_id})

    protocol_name = msg.protocol.value if hasattr(msg.protocol, "value") else str(msg.protocol)
    subsystem_name = msg.subsystem.value if hasattr(msg.subsystem, "value") else str(msg.subsystem)

    gate = check_and_prepare(msg)
    gate_status_tracker.record(
        gate.accepted,
        msg.device_id,
        None if gate.accepted else "; ".join(gate.report.violations),
    )
    if not gate.accepted:
        provenance_audit.record_attempt(
            ingest_id=ingest_id,
            device_id=msg.device_id,
            protocol=protocol_name,
            observation_timestamp=datetime.now(timezone.utc),
            kg_written=False,
            error="SHACL gate rejected: " + "; ".join(gate.report.violations),
        )
        raise HTTPException(
            status_code=422,
            detail={"error": "Semantic validation failed", "violations": gate.report.violations},
        )

    record_id = insert_sensor_data(msg)

    flattened = [
        {
            "type": m.type.value if hasattr(m.type, "value") else str(m.type),
            "value": m.value,
            "unit": m.unit.value if hasattr(m.unit, "value") else str(m.unit),
        }
        for m in msg.measurements
    ]

    if msg.measurements:
        first_m = msg.measurements[0]
        device = LiveDevice(
            device_id=msg.device_id,
            subsystem=subsystem_name,
            protocol=protocol_name,
            measurement_types=[first_m.type.value if hasattr(first_m.type, "value") else str(first_m.type)],
        )
        if aas_registry.observe(device):
            background_tasks.add_task(register_device_in_fuseki, device, config.FUSEKI_ENDPOINT)

    fired_alerts = analyse_after_ingest(
        device_id=msg.device_id,
        subsystem=subsystem_name,
        protocol=protocol_name,
        measurements=flattened,
    )

    ctx_alerts = []
    if gate.graph is not None:
        for entry in flattened:
            ctx_alerts.extend(
                evaluate_with_context(
                    device_id=msg.device_id,
                    observable_property=_observable_property(entry["type"]),
                    value=entry["value"],
                    graph=gate.graph,
                )
            )
        for a in ctx_alerts:
            logger.warning("Context alert: %s", a.message)

    analytics_result = run_prediction_pipeline(
        device_id=msg.device_id,
        subsystem=subsystem_name,
        protocol=protocol_name,
        measurements=[
            {"type": entry["type"], "value": entry["value"]} for entry in flattened
        ],
    )

    kg_written = await write_to_fuseki(msg, config.FUSEKI_ENDPOINT)

    provenance_audit.record_attempt(
        ingest_id=ingest_id,
        device_id=msg.device_id,
        protocol=protocol_name,
        observation_timestamp=datetime.now(timezone.utc),
        kg_written=kg_written,
        error=None if kg_written else "Fuseki unreachable",
    )

    return {
        "status": "ok",
        "record_id": record_id,
        "ingest_id": ingest_id,
        "device_id": msg.device_id,
        "kg_written": kg_written,
        "anomaly_alerts": len(fired_alerts),
        "semantic_alerts": len(ctx_alerts),
        "predictions": analytics_result["predictions"],
        "hazards": analytics_result["hazards"],
        "agv": analytics_result["agv"],
    }