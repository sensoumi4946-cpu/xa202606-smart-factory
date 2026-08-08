# GET /api/v1/history — time-range sensor data query with pagination.

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.store import query_history

router = APIRouter()


@router.get("/api/v1/history")
async def history(
    device_id: Optional[str] = Query(None),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    if since is not None and until is not None and until < since:
        raise HTTPException(status_code=422, detail="until must be >= since")
    return query_history(
        device_id=device_id,
        since=since.isoformat() if since else None,
        until=until.isoformat() if until else None,
        limit=limit,
        offset=offset,
    )
