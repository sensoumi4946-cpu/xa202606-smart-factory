# GET /api/v1/latest — latest measurement aggregation endpoint.
#
# Aggregates measurements across sensor_data records: for each
# (device_id, measurement.type) pair the value from the record with the
# newest timestamp is returned, grouped by device_id.
from typing import Optional

from fastapi import APIRouter, Query

from backend.store import get_latest

router = APIRouter()


@router.get("/api/v1/latest")
async def latest(device_id: Optional[str] = Query(None)):
    return get_latest(device_id=device_id)
