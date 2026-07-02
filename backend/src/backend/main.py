# FastAPI application entry point.
#
# Composes the three API routers (ingest, query, control) into a single
# ASGI application. Uses the modern lifespan context manager for startup
# (DB init) rather than the deprecated on_event hook.
#
# Error logging: all unhandled exceptions are caught by the global handler
# and printed as JSON Lines to stderr for container log aggregation.
import json
import sys
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.api.alerts import router as alerts_router
from backend.api.control import router as control_router
from backend.api.history import router as history_router
from backend.api.ingest import router as ingest_router
from backend.api.latest import router as latest_router
from backend.api.query import router as query_router
from backend.store import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="XA-202606 Smart Factory Backend", version="0.1.0", lifespan=lifespan
)

app.include_router(ingest_router)
app.include_router(query_router)
app.include_router(control_router)
app.include_router(latest_router)
app.include_router(history_router)
app.include_router(alerts_router)


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
