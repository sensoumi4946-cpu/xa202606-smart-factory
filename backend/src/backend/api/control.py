# Remote control endpoints.

from fastapi import APIRouter, HTTPException, Query, status

from backend.models import (
    ControlAckRequest,
    ControlListResponse,
    ControlRequest,
    ControlResponse,
    ControlStatusResponse,
)
from backend.services.control_dispatcher import dispatch
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


@router.post(
    "/api/v1/control",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ControlResponse,
)
async def control(req: ControlRequest):
    command_id = insert_control_command(req.device_id, req.action, req.params)

    published = await dispatch(
        command_id=command_id,
        device_id=req.device_id,
        action=req.action,
        params=req.params,
        subsystem=req.subsystem,
    )
    mark_command_dispatched(command_id, published)

    return ControlResponse(
        command_id=command_id,
        status="dispatched" if published else "failed",
        dispatched=published,
    )


@router.post("/api/v1/control/{command_id}/ack", response_model=ControlStatusResponse)
async def control_ack(command_id: str, req: ControlAckRequest):
    cmd = ack_control_command(command_id, req.success, req.detail)
    if cmd is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="command not found"
        )
    return _to_status_response(cmd)


@router.get("/api/v1/control", response_model=ControlListResponse)
async def control_log(
    device_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    cmds = list_control_commands(device_id=device_id, limit=limit)
    return ControlListResponse(items=[_to_status_response(c) for c in cmds])


@router.get("/api/v1/control/{command_id}", response_model=ControlStatusResponse)
async def control_status(command_id: str):
    cmd = get_control_status(command_id)
    if cmd is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="command not found"
        )
    return _to_status_response(cmd)
