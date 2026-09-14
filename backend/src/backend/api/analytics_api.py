

from __future__ import annotations

import time
from collections import deque
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from analytics.anomaly_detector import AnomalyDetector
from analytics.cross_subsystem_correlator import CrossSubsystemCorrelator
from analytics import trend_forecast
from analytics.thresholds import resolver
from backend.services.forecast_evaluation import (
    backtest_summary,
    forecast_history as query_forecast_history,
    forecast_quality_map,
    restore_windows,
)

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


@router.get("/api/v1/forecast-status")
async def forecast_status(horizon_minutes: float = 10.0) -> dict[str, Any]:
    restore_windows()
    quality_by_series = forecast_quality_map()
    items: list[dict[str, Any]] = []

    for tracked in trend_forecast.tracked_series():
        device_id = tracked["device_id"]
        property_name = tracked["property_name"]
        threshold_spec = resolver.threshold_for(property_name)

        # Boolean states and counters are not continuous fault forecasts.
        if threshold_spec is None or property_name in {"occupancy", "light_state", "count"}:
            continue

        threshold, direction = threshold_spec
        forecast = trend_forecast.forecast(
            device_id,
            property_name,
            horizon_minutes=horizon_minutes,
            threshold=threshold,
        ).to_dict()

        current = forecast.get("current_value")
        breached = (
            current is not None
            and (
                current >= threshold
                if direction == "above"
                else current <= threshold
            )
        )
        minutes_to = forecast.get("minutes_to_threshold")
        significant = bool(forecast.get("significant"))

        if breached:
            state = "breached"
        elif significant and minutes_to is not None and 0 <= minutes_to <= horizon_minutes:
            state = "predicted_breach"
        elif significant and minutes_to is not None and minutes_to > horizon_minutes:
            state = "watch"
        else:
            state = "stable"

        quality = quality_by_series.get((device_id, property_name), {})
        forecast["direction"] = direction
        forecast["state"] = state
        forecast["model_quality"] = quality.get(
            "model_quality",
            "insufficient_data",
        )
        forecast["backtest_evaluated"] = quality.get("evaluated", 0)
        forecast["backtest_normalized_mae"] = quality.get("normalized_mae")
        forecast["backtest_interval_coverage_95"] = quality.get(
            "interval_coverage_95"
        )
        items.append(forecast)

    priority = {"predicted_breach": 0, "breached": 1, "watch": 2, "stable": 3}
    items.sort(key=lambda item: (
        priority.get(item["state"], 9),
        item.get("minutes_to_threshold")
        if item.get("minutes_to_threshold") is not None
        else float("inf"),
    ))

    return {
        "horizon_minutes": horizon_minutes,
        "models": len(items),
        "items": items,
    }


@router.get("/api/v1/forecast-backtest")
async def forecast_backtest(
    days: int = Query(7, ge=1, le=90),
    device_id: str | None = None,
    property_name: str | None = None,
) -> dict[str, Any]:
    return backtest_summary(
        days=days,
        device_id=device_id,
        property_name=property_name,
    )


@router.get("/api/v1/forecast-history")
async def forecast_history_endpoint(
    device_id: str = Query(..., min_length=1, max_length=128),
    property_name: str | None = Query(None, min_length=1, max_length=128),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    return query_forecast_history(
        device_id=device_id,
        property_name=property_name,
        limit=limit,
    )


@router.get("/api/v1/trend")
async def trends():
    return {"series": trend_forecast.tracked_series()}


detector = _detector
correlator = _correlator
alert_history = _alert_history
