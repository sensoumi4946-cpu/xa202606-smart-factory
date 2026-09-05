

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from backend.security import command_audit, device_keys

router = APIRouter(prefix="/api/v1/security", tags=["security"])


class EnrollRequest(BaseModel):
    device_id: str = Field(..., min_length=1)
    scopes: list[str] = Field(default_factory=lambda: [device_keys.SCOPE_INGEST])


@router.post("/devices/enroll", status_code=status.HTTP_201_CREATED)
async def enroll(req: EnrollRequest) -> dict[str, Any]:
    try:
        return device_keys.enroll_device(req.device_id, req.scopes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/devices/keys")
async def keys(device_id: Optional[str] = None) -> dict[str, Any]:
    items = device_keys.list_keys(device_id)
    return {"items": items, "total": len(items)}


@router.post("/devices/keys/{key_id}/revoke")
async def revoke(key_id: str) -> dict[str, Any]:
    if not device_keys.revoke_key(key_id):
        raise HTTPException(status_code=404, detail="key not found or already revoked")
    return {"key_id": key_id, "revoked": True}


@router.post("/devices/keys/{key_id}/rotate")
async def rotate(key_id: str) -> dict[str, Any]:
    result = device_keys.rotate_key(key_id)
    if result is None:
        raise HTTPException(status_code=404, detail="key not found")
    return result


@router.post("/devices/{device_id}/revoke-all")
async def revoke_all(device_id: str) -> dict[str, Any]:
    count = device_keys.revoke_device(device_id)
    return {"device_id": device_id, "revoked_count": count}


@router.get("/whoami")
async def whoami(request: Request) -> dict[str, Any]:
    raw = request.headers.get("X-API-Key", "")
    identity = device_keys.resolve_key(raw)
    if identity is None:
        raise HTTPException(status_code=401, detail="unknown or revoked key")
    return identity


@router.get("/audit")
async def audit(
    device_id: Optional[str] = None,
    command_id: Optional[str] = None,
    actor: Optional[str] = None,
    outcome: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
) -> dict[str, Any]:
    items = command_audit.query(
        device_id=device_id,
        command_id=command_id,
        actor=actor,
        outcome=outcome,
        limit=limit,
    )
    return {"items": items, "total": len(items)}


@router.get("/audit/verify")
async def audit_verify() -> dict[str, Any]:
    return command_audit.verify_chain()
