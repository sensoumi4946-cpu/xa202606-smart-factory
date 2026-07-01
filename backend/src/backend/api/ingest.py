from fastapi import APIRouter, status
from smart_factory_contracts.messages import UnifiedMessage

from backend.models import IngestResponse
from backend.store import insert_sensor_data

router = APIRouter()


@router.post("/api/v1/data", status_code=status.HTTP_201_CREATED, response_model=IngestResponse)
async def ingest(msg: UnifiedMessage):
    record_id = insert_sensor_data(msg)
    return IngestResponse(id=record_id)
