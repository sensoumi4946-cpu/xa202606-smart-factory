from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.db import pool_stats, schema_version
from backend.middleware import metrics
from backend.services import device_health
from backend.store import get_device_registry, get_latest
from backend.config import LATEST_WINDOW_MINUTES

router = APIRouter(tags=["ops"])

FRESH_SECONDS = 120


@router.get("/metrics")
async def get_metrics() -> dict[str, Any]:
    return {
        **metrics.snapshot(),
        "database": {**pool_stats(), "schema_version": schema_version()},
    }


@router.post("/metrics/reset")
async def reset_metrics() -> dict[str, str]:
    metrics.reset()
    return {"status": "reset"}


def _reachable(last_seen: Optional[str]) -> bool:
    if not last_seen:
        return False
    from datetime import datetime, timezone

    try:
        seen = datetime.fromisoformat(last_seen)
    except ValueError:
        return False
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - seen).total_seconds() < FRESH_SECONDS


@router.get("/api/v1/devices/detail")
async def devices_detail() -> dict[str, Any]:
    registry = {d["device_id"]: d for d in get_device_registry()}
    health_rows = {h["device_id"]: h for h in device_health.list_health()}

    latest_counts: dict[str, int] = {}
    for entry in get_latest():
        latest_counts[entry["device_id"]] = len(entry.get("measurements", []))

    items = []
    for device_id in sorted(set(registry) | set(health_rows)):
        reg = registry.get(device_id, {})
        health = health_rows.get(
            device_id,
            {
                "device_id": device_id,
                "device_status": None,
                "error_code": None,
                "sensor_status": None,
                "firmware": None,
                "mac": None,
                "first_seen": None,
                "last_seen": None,
                "message_count": 0,
            },
        )
        last_seen = reg.get("last_seen") or health.get("last_seen")
        enriched = device_health.enrich(dict(health), _reachable(last_seen))
        items.append(
            {
                **enriched,
                "device_id": device_id,
                "subsystem": reg.get("subsystem", ""),
                "protocol": reg.get("protocol", ""),
                "last_seen": last_seen,
                "active_properties": latest_counts.get(device_id, 0),
            }
        )

    unhealthy = [i for i in items if i.get("healthy") is False or not i["reachable"]]
    return {
        "items": items,
        "total": len(items),
        "unhealthy": len(unhealthy),
        "window_minutes": LATEST_WINDOW_MINUTES,
    }


@router.get("/api/v1/devices/{device_id}/health")
async def device_detail(device_id: str) -> dict[str, Any]:
    record = device_health.get_health(device_id)
    if record is None:
        raise HTTPException(status_code=404, detail="no health record for device")
    registry = {d["device_id"]: d for d in get_device_registry()}
    last_seen = registry.get(device_id, {}).get("last_seen") or record.get("last_seen")
    return device_health.enrich(dict(record), _reachable(last_seen))


@router.post("/api/v1/devices/{device_id}/health")
async def report_health(
    device_id: str,
    device_status: int = Query(..., ge=0, le=65535),
    error_code: int = Query(..., ge=0, le=65535),
    sensor_status: int = Query(..., ge=0, le=65535),
    firmware: Optional[str] = None,
    mac: Optional[str] = None,
) -> dict[str, Any]:
    decoded = device_health.record_health(
        device_id,
        status_words=[device_status, error_code, sensor_status],
        firmware=firmware,
        mac=mac,
    )
    return {"device_id": device_id, **decoded}
