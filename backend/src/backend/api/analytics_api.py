

from __future__ import annotations

import time
from collections import deque
import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from analytics.anomaly_detector import AnomalyDetector
from analytics.cross_subsystem_correlator import CrossSubsystemCorrelator
from analytics import trend_forecast
from analytics.thresholds import resolver

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])


_detector = AnomalyDetector(window_size=30, z_threshold=3.0)
_correlator = CrossSubsystemCorrelator(window_seconds=10.0, min_sources=2)

_alert_history = deque(maxlen=1000)


class _ReadingIn:
    pass


@router.post("/reading")
async def analyse_reading(body: dict[str, Any]) -> dict[str, Any]:
    
    sensor_id = body.get("sensor_id")
    value = body.get("value")
    if sensor_id is None or value is None:
        raise HTTPException(status_code=422, detail="sensor_id and value are required")

    try:
        value = float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="value must be numeric")

    property_name = body.get("property_name", "")
    subsystem = body.get("subsystem", "unknown")
    protocol = body.get("protocol", "unknown")

    result = _detector.push_reading(
        sensor_id=sensor_id,
        value=value,
        property_name=property_name,
    )

    new_alerts = []
    if result.is_anomaly:
        fired = _correlator.push_anomaly(
            result=result,
            subsystem=subsystem,
            protocol=protocol,
            property_name=property_name,
        )
        for alert in fired:
            record = {
                "alert_id": alert.alert_id,
                "triggered_at": alert.triggered_at,
                "hypothesis": alert.hypothesis,
                "confidence": alert.confidence,
                "subsystems": alert.subsystems_involved,
                "protocols": alert.protocols_involved,
                "sources": alert.sources,
            }
            _alert_history.append(record)
            new_alerts.append(record)

    return {
        "sensor_id": sensor_id,
        "value": value,
        "is_anomaly": result.is_anomaly,
        "z_score": result.z_score,
        "severity": result.severity,
        "reason": result.reason,
        "correlated_alerts_fired": new_alerts,
    }


@router.get("/alerts")
async def get_alerts(limit: int = 50) -> dict[str, Any]:
    
    recent = list(_alert_history)[-limit:]
    return {
        "total": len(_alert_history),
        "returned": len(recent),
        "alerts": list(reversed(recent)),
    }


@router.delete("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str) -> dict[str, Any]:
    
    _correlator.clear_alert(alert_id)
    return {"alert_id": alert_id, "acknowledged": True}


@router.get("/sensors/{sensor_id}/stats")
async def sensor_stats(sensor_id: str) -> dict[str, Any]:
    
    stats = _detector.sensor_stats(sensor_id)
    return stats


@router.get("/pending")
async def pending_anomalies() -> dict[str, Any]:
    
    pending = _correlator.pending_anomalies()
    return {
        "window_seconds": _correlator.window_seconds,
        "pending_count": len(pending),
        "items": pending,
    }
@router.get("/api/v1/trend/{device_id}/{property_name}")
async def trend(device_id: str, property_name: str, horizon_minutes: float = 10.0):
    threshold = resolver.threshold_for(property_name)
    return trend_forecast.forecast(
        device_id,
        property_name,
        horizon_minutes=horizon_minutes,
        threshold=threshold[0] if threshold else None,
    ).to_dict()


@router.get("/api/v1/trend")
async def trends():
    return {"series": trend_forecast.tracked_series()}


detector = _detector
correlator = _correlator
alert_history = _alert_history
