# FastAPI request/response Pydantic models for the backend API.

from typing import Optional

from pydantic import BaseModel, Field


class IngestResponse(BaseModel):
    id: str


class ControlRequest(BaseModel):
    device_id: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    params: dict = Field(default_factory=dict)
    # Used to build the MQTT topic: factory/{subsystem}/control/{device_id}
    subsystem: str = Field(default="actuator", min_length=1)


class ControlResponse(BaseModel):
    command_id: str
    status: str = "pending"
    dispatched: bool = False


class ControlAckRequest(BaseModel):
    success: bool = True
    detail: str = ""


class ControlStatusResponse(BaseModel):
    command_id: str
    device_id: str
    action: str
    status: str
    created_at: str
    dispatched_at: Optional[str] = None
    acked_at: Optional[str] = None
    result: Optional[str] = None


class ControlListResponse(BaseModel):
    items: list[ControlStatusResponse]
