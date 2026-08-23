import asyncio
import json
import logging
import sys
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend import config
from backend.api.innovation_api import load_bindings
from backend.api.routes import api_router
from backend.middleware import RequestContextMiddleware
from backend.runtime_state import assert_single_worker
from backend.security.auth import api_key_middleware
from backend.services.registry_singleton import aas_registry, provenance_audit
from backend.services.retry_service import retry_loop
from backend.store import init_db
from semantic_layer.aas_bridge import write_aas_to_fuseki
from semantic_layer.aas_live_sync import watch_loop as aas_watch_loop

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    assert_single_worker()
    init_db()
    from analytics.thresholds import autobind

    autobind()

    binding_count = load_bindings()
    if binding_count == 0:
        logger.error(
            "no protocol bindings loaded — ontology-driven adapter generation is "
            "DISABLED; check that bindings.ttl is at the repo root"
        )
    else:
        logger.info("loaded %d protocol bindings", binding_count)

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
app.include_router(api_router)
app.add_middleware(RequestContextMiddleware)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log_entry = {
        "service": "backend",
        "event": "unhandled_error",
        "level": "error",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "path": str(request.url.path),
        "error": str(exc),
        "traceback": traceback.format_exc(),
    }
    print(json.dumps(log_entry), file=sys.stderr)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})