

from typing import Optional

from fastapi import APIRouter, Query

from backend.store import get_devices, get_device_registry, query_sensor_data

router = APIRouter()


@router.get("/api/v1/data")
async def query(
    device_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    since: Optional[str] = Query(None),
):
    rows = query_sensor_data(device_id=device_id, limit=limit, since=since)
    return rows


@router.get("/api/v1/devices")
async def devices():
    return get_devices()


@router.get("/api/v1/devices/registry")
async def devices_registry():
    return get_device_registry()
