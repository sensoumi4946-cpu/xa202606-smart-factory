from fastapi import APIRouter, HTTPException, status

from backend.models import ControlRequest, ControlResponse, ControlStatusResponse
from backend.store import get_control_status, insert_control_command

router = APIRouter()


@router.post("/api/v1/control", status_code=status.HTTP_202_ACCEPTED, response_model=ControlResponse)
async def control(req: ControlRequest):
    command_id = insert_control_command(req.device_id, req.action, req.params)
    return ControlResponse(command_id=command_id)


@router.get("/api/v1/control/{command_id}", response_model=ControlStatusResponse)
async def control_status(command_id: str):
    cmd = get_control_status(command_id)
    if cmd is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="command not found")
    return ControlStatusResponse(
        command_id=cmd["command_id"],
        device_id=cmd["device_id"],
        action=cmd["action"],
        status=cmd["status"],
        created_at=cmd["created_at"],
    )
