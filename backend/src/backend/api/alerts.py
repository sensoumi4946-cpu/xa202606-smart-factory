



from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.store import acknowledge_alert, query_alerts

router = APIRouter()

VALID_LEVELS = {"warning", "critical"}
VALID_STATUSES = {"active", "acknowledged", "resolved", "all"}


@router.get("/api/v1/alerts")
async def alerts(
    device_id: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    status: str = Query("active"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    if level is not None and level not in VALID_LEVELS:
        raise HTTPException(
            status_code=422,
            detail=f"level must be one of {sorted(VALID_LEVELS)}",
        )
    if status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {sorted(VALID_STATUSES)}",
        )
    return query_alerts(
        device_id=device_id,
        level=level,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.post("/api/v1/alerts/{alert_id}/acknowledge")
async def acknowledge(alert_id: str) -> dict[str, object]:
    if not acknowledge_alert(alert_id):
        raise HTTPException(status_code=404, detail="active alert not found")
    return {"alert_id": alert_id, "status": "acknowledged"}
