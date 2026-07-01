# FastAPI request/response Pydantic models for the backend API.
# Note: the wire-format UnifiedMessage lives in shared/, not here.
from pydantic import BaseModel, Field


class IngestResponse(BaseModel):
    id: str


class ControlRequest(BaseModel):
    device_id: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    params: dict = Field(default_factory=dict)


class ControlResponse(BaseModel):
    command_id: str


class ControlStatusResponse(BaseModel):
    command_id: str
    device_id: str
    action: str
    status: str
    created_at: str
