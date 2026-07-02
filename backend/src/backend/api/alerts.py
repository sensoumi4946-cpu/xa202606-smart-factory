# GET /api/v1/alerts — alert query endpoint with filtering and pagination.
#
# Supports optional device_id and level filters. level must be one of
# "warning" or "critical" — any other value returns 422.
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.store import query_alerts

router = APIRouter()

VALID_LEVELS = {"warning", "critical"}


@router.get("/api/v1/alerts")
async def alerts(
    device_id: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    if level is not None and level not in VALID_LEVELS:
        raise HTTPException(
            status_code=422,
            detail=f"level must be one of {sorted(VALID_LEVELS)}",
        )
    return query_alerts(
        device_id=device_id, level=level, limit=limit, offset=offset
    )
