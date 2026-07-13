# Receives sensor readings from adapters and writes them to Fuseki.

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import config
from backend.services.fuseki_client import write_to_fuseki
from semantic_layer.observation_gate import check_and_prepare

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
async def ingest_reading(reading: SensorReading) -> dict[str, Any]:
    raw = reading.model_dump()

    result = check_and_prepare(raw)

    if not result["accepted"]:
        logger.warning(
            "Rejected reading from %s — %s",
            reading.sensor_id,
            result.get("reason", "unknown"),
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Observation failed semantic validation",
                "reason": result.get("reason"),
                "violations": result.get("violations", []),
            },
        )

    try:
        write_to_fuseki(
            endpoint=config.FUSEKI_ENDPOINT,
            triples=result["triples"],
        )
    except Exception as exc:
        logger.exception("Fuseki write failed for sensor %s", reading.sensor_id)
        raise HTTPException(
            status_code=503,
            detail="Could not write to knowledge graph — Fuseki unreachable",
        ) from exc

    logger.debug("Wrote %d triples for %s", len(result["triples"]), reading.sensor_id)

    return {
        "status": "ok",
        "sensor_id": reading.sensor_id,
        "triples_written": len(result["triples"]),
        "observation_uri": result.get("observation_uri"),
    }


@router.post("/batch")
async def ingest_batch(readings: list[SensorReading]) -> dict[str, Any]:
    
    accepted = []
    rejected = []

    for reading in readings:
        raw = reading.model_dump()
        result = check_and_prepare(raw)

        if not result["accepted"]:
            rejected.append(
                {
                    "sensor_id": reading.sensor_id,
                    "reason": result.get("reason"),
                }
            )
            continue

        try:
            write_to_fuseki(
                endpoint=config.FUSEKI_ENDPOINT,
                triples=result["triples"],
            )
            accepted.append(reading.sensor_id)
        except Exception:
            logger.exception("Fuseki write failed for %s during batch", reading.sensor_id)
            rejected.append(
                {
                    "sensor_id": reading.sensor_id,
                    "reason": "Fuseki write error",
                }
            )

    return {
        "total": len(readings),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "rejected_detail": rejected,
    }
