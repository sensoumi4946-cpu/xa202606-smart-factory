import hashlib
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, status

from backend.models import (
    ControlAckRequest,
    ControlListResponse,
    ControlRequest,
    ControlResponse,
    ControlStatusResponse,
)
from backend.security import command_audit, command_signing
from backend.services import failsafe
from backend.services import control_dispatcher
from backend.store import (
    ack_control_command,
    get_control_status,
    insert_control_command,
    list_control_commands,
    mark_command_dispatched,
)

router = APIRouter()


def _to_status_response(cmd: dict) -> ControlStatusResponse:
    return ControlStatusResponse(
        command_id=cmd["command_id"],
        device_id=cmd["device_id"],
        action=cmd["action"],
        status=cmd["status"],
        created_at=cmd["created_at"],
        dispatched_at=cmd.get("dispatched_at"),
        acked_at=cmd.get("acked_at"),
        result=cmd.get("result"),
    )


def _actor(request: Request) -> tuple[str, Optional[str]]:
    key = request.headers.get("X-API-Key")
    return ("api-key" if key else "anonymous", hashlib.sha256(key.encode()).hexdigest()[:12] if key else None)


def _source_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.post(
    "/api/v1/control",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ControlResponse,
)
async def control(req: ControlRequest, request: Request):
    actor, actor_key_id = _actor(request)
    source_ip = _source_ip(request)

    command_id = insert_control_command(req.device_id, req.action, req.params)

    envelope = control_dispatcher.build_payload(
        command_id, req.device_id, req.action, req.params or {}
    )
    signed = command_signing.enabled()
    if signed:
        envelope = command_signing.attach_signature(envelope)

    published = await control_dispatcher.dispatch(
        command_id=command_id,
        device_id=req.device_id,
        action=req.action,
        params=req.params,
        subsystem=req.subsystem,
        payload=envelope,
    )
    mark_command_dispatched(command_id, published)

    command_audit.record(
        device_id=req.device_id,
        action=req.action,
        outcome="dispatched" if published else "dispatch_failed",
        actor=actor,
        command_id=command_id,
        params=req.params,
        actor_key_id=actor_key_id,
        source_ip=source_ip,
    )

    return ControlResponse(
        command_id=command_id,
        status="dispatched" if published else "failed",
        dispatched=published,
    )


@router.post("/api/v1/control/{command_id}/ack", response_model=ControlStatusResponse)
async def control_ack(command_id: str, req: ControlAckRequest, request: Request):
    cmd = ack_control_command(command_id, req.success, req.detail)
    if cmd is None:
        raise HTTPException(status_code=404, detail=f"unknown command {command_id}")

    actor, actor_key_id = _actor(request)
    command_audit.record(
        device_id=cmd["device_id"],
        action=cmd["action"],
        outcome="acked" if req.success else "ack_failed",
        actor=actor,
        command_id=command_id,
        params={"detail": req.detail} if req.detail else None,
        actor_key_id=actor_key_id,
        source_ip=_source_ip(request),
    )
    return _to_status_response(cmd)


@router.get("/api/v1/control", response_model=ControlListResponse)
async def control_log(
    device_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    commands = list_control_commands(device_id=device_id, limit=limit)
    return ControlListResponse(items=[_to_status_response(c) for c in commands])


@router.get("/api/v1/control/{command_id}", response_model=ControlStatusResponse)
async def control_status(command_id: str):
    cmd = get_control_status(command_id)
    if cmd is None:
        raise HTTPException(status_code=404, detail=f"unknown command {command_id}")
    return _to_status_response(cmd)


@router.get("/api/v1/control/signing/status")
async def signing_status():
    return {
        "enabled": command_signing.enabled(),
        "algorithm": "HMAC-SHA256-HEX" if command_signing.enabled() else None,
        "signed_fields": list(command_signing.SIGNED_FIELDS),
    }


@router.get("/api/v1/failsafe/{device_id}")
async def failsafe_state(device_id: str):
    spec = failsafe.spec_for(device_id)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"no failsafe spec for {device_id}")
    return failsafe.heartbeat_payload(device_id)
