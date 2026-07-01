from pydantic import BaseModel, Field

from smart_factory_contracts.messages import UnifiedMessage


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
