# Receives sensor readings from adapters and writes them to Fuseki.

import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend import config
from semantic_layer.fuseki import write_to_fuseki
from semantic_layer.observation_gate import check_and_prepare
from semantic_layer.semantic_context_rules import evaluate_with_context
from semantic_layer.semantic_provenance_audit import ProvenanceAuditLog
from semantic_layer.aas_live_sync import AASRegistry, LiveDevice, register_device_in_fuseki
from datetime import datetime, timezone

_audit  = ProvenanceAuditLog()   
_aas_registry = AASRegistry()    

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingest"])


class SensorReading(BaseModel):
    sensor_id: str
    subsystem: str       
    protocol: str        # "MQTT", "OPC-UA", "Modbus", "CoAP"
    property_name: str   
    value: float
    unit: str
    timestamp: str       # ISO-8601 string, e.g. "2025-03-15T10:30:00Z"
@router.post("/reading")
async def ingest_reading(reading: SensorReading, background_tasks: BackgroundTasks) -> dict[str, Any]:
    ingest_id = str(uuid.uuid4())

    from smart_factory_contracts.messages import (
        Measurement, MeasurementType, Protocol, Subsystem, Unit, UnifiedMessage,
    )
    from datetime import datetime, timezone as _tz

    _mtype_map = {
        "temperature": MeasurementType.TEMPERATURE,
        "humidity": MeasurementType.HUMIDITY,
        "co": MeasurementType.CO,
        "smoke": MeasurementType.SMOKE,
        "combustible_gas": MeasurementType.COMBUSTIBLE_GAS,
        "distance": MeasurementType.DISTANCE,
        "count": MeasurementType.COUNT,
        "occupancy": MeasurementType.OCCUPANCY,
        "light_state": MeasurementType.LIGHT_STATE,
    }
    _unit_map = {
        "celsius": Unit.CELSIUS, "percent": Unit.PERCENT,
        "ppm": Unit.PPM, "cm": Unit.CM, "count": Unit.COUNT, "boolean": Unit.BOOLEAN,
    }
    _proto_map = {
        "mqtt": Protocol.MQTT, "modbus": Protocol.MODBUS,
        "opcua": Protocol.OPCUA, "rest": Protocol.REST,
    }
    _sub_map = {
        "temp_humidity": Subsystem.TEMP_HUMIDITY, "lighting": Subsystem.LIGHTING,
        "gas": Subsystem.GAS, "agv": Subsystem.AGV, "counting": Subsystem.COUNTING,
    }

    try:
        unified_msg = UnifiedMessage(
            schema_version="v1",
            device_id=reading.sensor_id,
            subsystem=_sub_map.get(reading.subsystem.lower(), Subsystem.GAS),
            protocol=_proto_map.get(reading.protocol.lower(), Protocol.MQTT),
            timestamp=datetime.now(_tz.utc),
            measurements=[Measurement(
                type=_mtype_map.get(reading.property_name.lower(), MeasurementType.TEMPERATURE),
                value=reading.value,
                unit=_unit_map.get(reading.unit.lower(), Unit.CELSIUS),
            )],
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not build UnifiedMessage: {exc}") from exc

    gate = check_and_prepare(unified_msg)

    if not gate.accepted:
        _audit.record_attempt(
            ingest_id=ingest_id,
            device_id=reading.sensor_id,
            protocol=reading.protocol,
            observation_timestamp=datetime.now(_tz.utc),
            kg_written=False,
            error="SHACL gate rejected",
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Observation failed semantic validation",
                "violations": gate.report.violations,
                "warnings": gate.report.warnings,
            },
        )

    if gate.graph is not None:
        ctx_alerts = evaluate_with_context(
            device_id=reading.sensor_id,
            observable_property=f"measures{reading.property_name.capitalize()}",
            value=reading.value,
            graph=gate.graph,
        )
        for alert in ctx_alerts:
            logger.warning("Semantic alert: %s", alert.message)

    device = LiveDevice(
        device_id=reading.sensor_id,
        subsystem=reading.subsystem,
        protocol=reading.protocol.lower(),
        measurement_types=[reading.property_name],
    )
    if _aas_registry.observe(device):
        background_tasks.add_task(register_device_in_fuseki, device, config.FUSEKI_ENDPOINT)

    kg_written = await write_to_fuseki(unified_msg, config.FUSEKI_ENDPOINT)

    from datetime import datetime as _dt
    _audit.record_attempt(
        ingest_id=ingest_id,
        device_id=reading.sensor_id,
        protocol=reading.protocol,
        observation_timestamp=datetime.now(_tz.utc),
        kg_written=kg_written,
        error=None if kg_written else "Fuseki unreachable",
    )

    return {
        "status": "ok",
        "sensor_id": reading.sensor_id,
        "ingest_id": ingest_id,
        "kg_written": kg_written,
    }


@router.post("/batch")
async def ingest_batch(readings: list[SensorReading], background_tasks: BackgroundTasks) -> dict[str, Any]:
    accepted, rejected = [], []
    for r in readings:
        try:
            result = await ingest_reading(r, background_tasks)
            accepted.append(r.sensor_id)
        except HTTPException as exc:
            rejected.append({"sensor_id": r.sensor_id, "reason": str(exc.detail)})
    return {"total": len(readings), "accepted": len(accepted), "rejected": len(rejected), "rejected_detail": rejected}