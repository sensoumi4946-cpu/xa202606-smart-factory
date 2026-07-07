# POST /api/v1/data — sensor data ingestion endpoint.
#
# Accepts a UnifiedMessage, validates via Pydantic, stores in SQLite, then
# fires a best-effort semantic write to Fuseki through BackgroundTasks. The
# semantic write is decoupled from the SQLite path: if Fuseki is down the
# ingest still returns 201 and a semantic_write_failed warning is logged.
from fastapi import APIRouter, BackgroundTasks, status
from semantic_layer.fuseki import write_to_fuseki
from smart_factory_contracts.messages import UnifiedMessage

from backend import config
from backend.logs import log_json
from backend.models import IngestResponse
from backend.store import insert_sensor_data

router = APIRouter()


async def _semantic_write(msg: UnifiedMessage) -> None:
    ok = await write_to_fuseki(msg, config.FUSEKI_ENDPOINT)
    if not ok:
        log_json("semantic_write_failed", level="warning", device_id=msg.device_id)


@router.post(
    "/api/v1/data", status_code=status.HTTP_201_CREATED, response_model=IngestResponse
)
async def ingest(msg: UnifiedMessage, background_tasks: BackgroundTasks):
    record_id = insert_sensor_data(msg)
    if config.SEMANTIC_WRITE_ENABLED:
        background_tasks.add_task(_semantic_write, msg)
    return IngestResponse(id=record_id)
