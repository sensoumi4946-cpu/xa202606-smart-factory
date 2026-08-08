import json
import logging
import sys
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend import config
from backend.api.alerts    import router as alerts_router
from backend.api.control   import router as control_router
from backend.api.history   import router as history_router
from backend.api.ingest    import router as ingest_router
from backend.api.latest    import router as latest_router
from backend.api.query     import router as query_router
from backend.api.semantic  import router as semantic_router
from backend.api.aas       import router as aas_router
from backend.api.fire_risk import router as fire_risk_router
from backend.api.analytics_api import router as analytics_router
from backend.api.semantic_query import router as semantic_query_router
from backend.security.auth import api_key_middleware
from backend.api.federated import router as federated_router
from backend.api.provenance_api import router as provenance_router

from backend.store import init_db
from semantic_layer.aas_bridge import write_aas_to_fuseki
from backend.services.registry_singleton import aas_registry, provenance_audit
from semantic_layer.aas_live_sync import watch_loop as aas_watch_loop
from backend.services.retry_service import retry_loop
from backend.api.health_check import router as health_router
import asyncio

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seeded = await write_aas_to_fuseki(config.FUSEKI_ENDPOINT)
    if seeded:
        logger.info("AAS descriptors seeded into Fuseki")
    else:
        logger.warning("AAS seed skipped — Fuseki may not be ready yet")

    watch_task = asyncio.create_task(
        aas_watch_loop(aas_registry, config.FUSEKI_ENDPOINT, poll_interval_seconds=30.0)
    )
    retry_task = asyncio.create_task(
        retry_loop(provenance_audit, config.FUSEKI_ENDPOINT, interval_seconds=60.0)
    )
    yield
    watch_task.cancel()
    retry_task.cancel()
    for t in [watch_task, retry_task]:
        try:
            await t
        except asyncio.CancelledError:
            pass

app = FastAPI(
    title="XA-202606 Smart Factory Backend",
    version="0.1.0",
    lifespan=lifespan,
)
app.middleware("http")(api_key_middleware)

app.include_router(ingest_router)
app.include_router(query_router)
app.include_router(control_router)
app.include_router(latest_router)
app.include_router(history_router)
app.include_router(alerts_router)
app.include_router(semantic_router)
app.include_router(aas_router)
app.include_router(fire_risk_router)
app.include_router(analytics_router)
app.include_router(semantic_query_router)
app.include_router(federated_router)
app.include_router(provenance_router)
app.include_router(health_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log_entry = {
        "service":   "backend",
        "event":     "unhandled_error",
        "level":     "error",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "path":      str(request.url.path),
        "error":     str(exc),
        "traceback": traceback.format_exc(),
    }
    print(json.dumps(log_entry), file=sys.stderr)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})
