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
from analytics import trend_forecast
from semantic_layer.fuseki import write_to_fuseki
from semantic_layer.observation_gate import check_and_prepare
from semantic_layer.semantic_context_rules import evaluate_with_context
from semantic_layer.aas_live_sync import LiveDevice, register_device_in_fuseki
from smart_factory_contracts.messages import (
    Measurement,
    MeasurementType,
    Protocol,
    Subsystem,
    Unit,
    UnifiedMessage,
)
from backend.store import insert_sensor_data
from backend.api.prediction import process_reading as run_prediction_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingest"])

_MTYPE = {m.value: m for m in MeasurementType}
_UNIT = {u.value: u for u in Unit}
_PROTO = {p.value: p for p in Protocol}
_SUB = {s.value: s for s in Subsystem}


class SensorReading(BaseModel):
    sensor_id: str
    subsystem: str
    protocol: str
    property_name: str
    value: float
    unit: str
    timestamp: datetime


def _observable_property(property_name: str) -> str:
    parts = [p for p in property_name.split("_") if p]
    return "measures" + "".join(p.capitalize() for p in parts)


def _canonical_device_id(device_id: str, subsystem: str | None = None) -> str:
    from backend.api.innovation_api import binding_registry
    canonical = binding_registry.resolve_device_id(device_id)
    allowed = {b.canonical_subsystem for b in binding_registry.for_device(canonical)}
    if subsystem is not None and allowed and subsystem not in allowed:
        raise HTTPException(status_code=422, detail="device_id belongs to a different subsystem")
    return canonical


def _enum_value(field: Any) -> str:
    return field.value if hasattr(field, "value") else str(field)


async def _write_kg_and_audit(
    msg: UnifiedMessage,
    ingest_id: str,
    protocol_value: str,
    observed_at: datetime,
) -> None:
    if not config.SEMANTIC_WRITE_ENABLED:
        return
    kg_written = False
    error = None
    try:
        kg_written = await write_to_fuseki(msg, config.FUSEKI_ENDPOINT)
        if not kg_written:
            error = "Fuseki write returned false"
            logger.warning("KG write failed for %s: %s", msg.device_id, error)
    except Exception as exc:
        error = f"Fuseki write failed: {exc}"
        logger.warning("KG write failed for %s: %s", msg.device_id, exc)
    provenance_audit.record_attempt(
        ingest_id=ingest_id,
        device_id=msg.device_id,
        protocol=protocol_value,
        observation_timestamp=observed_at,
        kg_written=kg_written,
        error=error,
    )


def _to_unified(reading: SensorReading) -> UnifiedMessage:
    mtype = _MTYPE.get(reading.property_name.lower())
    unit = _UNIT.get(reading.unit.lower())
    proto = _PROTO.get(reading.protocol.lower())
    sub = _SUB.get(reading.subsystem.lower())

    if mtype is None:
        raise ValueError(
            f"Unknown property_name '{reading.property_name}'. Valid: {list(_MTYPE)}"
        )
    if unit is None:
        raise ValueError(f"Unknown unit '{reading.unit}'. Valid: {list(_UNIT)}")
    if proto is None:
        raise ValueError(
            f"Unknown protocol '{reading.protocol}'. Valid: {list(_PROTO)}"
        )
    if sub is None:
        raise ValueError(
            f"Unknown subsystem '{reading.subsystem}'. Valid: {list(_SUB)}"
        )

    return UnifiedMessage(
        schema_version="v1",
        device_id=_canonical_device_id(reading.sensor_id, reading.subsystem),
        subsystem=sub,
        protocol=proto,
        timestamp=reading.timestamp,
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

    observed_at = datetime.now(timezone.utc)
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
            protocol=reading.protocol,
            observation_timestamp=observed_at,
            kg_written=False,
            error="SHACL gate rejected: " + "; ".join(gate.report.violations),
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Semantic validation failed",
                "violations": gate.report.violations,
            },
        )

    record_id = insert_sensor_data(msg)
    ingest_id = record_id
    from backend.services.device_health import record_health
    status_values = {_enum_value(m.type): m.value for m in msg.measurements}
    names = ("device_status", "error_code", "sensor_status")
    words = [int(status_values[n]) for n in names] if all(n in status_values for n in names) else None
    record_health(msg.device_id, status_words=words)
    trend_forecast.record(msg.device_id, reading.property_name, reading.value, at=msg.timestamp)
    run_prediction_pipeline(msg.device_id, reading.subsystem, reading.protocol, [{"type": reading.property_name, "value": reading.value}], timestamp=msg.timestamp.timestamp())

    fired_alerts = analyse_after_ingest(
        device_id=msg.device_id,
        subsystem=reading.subsystem,
        protocol=reading.protocol,
        measurements=[
            {
                "type": reading.property_name,
                "value": reading.value,
                "unit": reading.unit,
            }
        ],
    )

    ctx_alerts = []
    if gate.graph is not None:
        ctx_alerts = evaluate_with_context(
            device_id=msg.device_id,
            observable_property=_observable_property(reading.property_name),
            value=reading.value,
            graph=gate.graph,
        )
        for a in ctx_alerts:
            logger.warning("Context alert: %s", a.message)

    device = LiveDevice(
        device_id=msg.device_id,
        subsystem=reading.subsystem,
        protocol=reading.protocol.lower(),
        measurement_types=[reading.property_name],
    )
    if config.SEMANTIC_WRITE_ENABLED and aas_registry.observe(device):
        background_tasks.add_task(
            register_device_in_fuseki, device, config.FUSEKI_ENDPOINT
        )

    background_tasks.add_task(
        _write_kg_and_audit, msg, ingest_id, reading.protocol, observed_at
    )

    return {
        "status": "ok",
        "record_id": record_id,
        "ingest_id": ingest_id,
        "device_id": msg.device_id,
        "reported_device_id": reading.sensor_id,
        "kg_write": "queued" if config.SEMANTIC_WRITE_ENABLED else "disabled",
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
            await ingest_reading(r, background_tasks)
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
    observed_at = datetime.now(timezone.utc)

    reported_device_id = msg.device_id
    canonical = _canonical_device_id(reported_device_id, _enum_value(msg.subsystem))
    if canonical != reported_device_id:
        msg = msg.model_copy(update={"device_id": canonical})
        logger.info(
            "device alias resolved via ontology: %s -> %s",
            reported_device_id,
            canonical,
        )

    subsystem_value = _enum_value(msg.subsystem)
    protocol_value = _enum_value(msg.protocol)

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
            protocol=protocol_value,
            observation_timestamp=observed_at,
            kg_written=False,
            error="SHACL gate rejected: " + "; ".join(gate.report.violations),
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Semantic validation failed",
                "violations": gate.report.violations,
            },
        )

    record_id = insert_sensor_data(msg)
    ingest_id = record_id
    from backend.services.device_health import record_health
    status_values = {_enum_value(m.type): m.value for m in msg.measurements}
    names = ("device_status", "error_code", "sensor_status")
    words = [int(status_values[n]) for n in names] if all(n in status_values for n in names) else None
    record_health(msg.device_id, status_words=words)

    if msg.measurements:
        first_m = msg.measurements[0]
        device = LiveDevice(
            device_id=msg.device_id,
            subsystem=subsystem_value,
            protocol=protocol_value,
            measurement_types=[_enum_value(m.type) for m in msg.measurements],
        )
        if config.SEMANTIC_WRITE_ENABLED and aas_registry.observe(device):
            background_tasks.add_task(
                register_device_in_fuseki, device, config.FUSEKI_ENDPOINT
            )

    measurement_dicts = [
        {
            "type": _enum_value(m.type),
            "value": m.value,
            "unit": _enum_value(m.unit),
        }
        for m in msg.measurements
    ]

    for m in measurement_dicts:
        trend_forecast.record(msg.device_id, m["type"], m["value"], at=msg.timestamp)

    analytics_result = run_prediction_pipeline(
        timestamp=msg.timestamp.timestamp(),
        device_id=msg.device_id,
        subsystem=subsystem_value,
        protocol=protocol_value,
        measurements=[
            {"type": m["type"], "value": m["value"]} for m in measurement_dicts
        ],
    )

    fired_alerts = analyse_after_ingest(
        device_id=msg.device_id,
        subsystem=subsystem_value,
        protocol=protocol_value,
        measurements=measurement_dicts,
    )

    ctx_alerts = []
    if gate.graph is not None:
        for m in measurement_dicts:
            ctx_alerts.extend(
                evaluate_with_context(
                    device_id=msg.device_id,
                    observable_property=_observable_property(m["type"]),
                    value=m["value"],
                    graph=gate.graph,
                )
            )
        for a in ctx_alerts:
            logger.warning("Context alert: %s", a.message)

    background_tasks.add_task(
        _write_kg_and_audit, msg, ingest_id, protocol_value, observed_at
    )

    return {
        "status": "ok",
        "record_id": record_id,
        "ingest_id": ingest_id,
        "device_id": msg.device_id,
        "reported_device_id": reported_device_id,
        "kg_write": "queued" if config.SEMANTIC_WRITE_ENABLED else "disabled",
        "anomaly_alerts": len(fired_alerts),
        "semantic_alerts": len(ctx_alerts),
        "predictions": analytics_result["predictions"],
        "hazards": analytics_result["hazards"],
        "agv": analytics_result["agv"],
    }
