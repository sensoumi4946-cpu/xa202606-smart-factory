




from typing import Optional

from fastapi import APIRouter, Query

from backend.store import get_latest

router = APIRouter()


@router.get("/api/v1/latest")
async def latest(device_id: Optional[str] = Query(None)):
    return get_latest(device_id=device_id)
