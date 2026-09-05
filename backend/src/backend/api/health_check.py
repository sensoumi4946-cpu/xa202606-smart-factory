

from __future__ import annotations

import sqlite3
from urllib.parse import urlsplit
import time
import logging
from typing import Any

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend import config

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


async def _check_fuseki() -> dict:
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
            resp = await client.get(
                urlsplit(config.FUSEKI_QUERY_URL)._replace(path="/$/ping", query="", fragment="").geturl()
            )
        ok = resp.status_code == 200
    except httpx.HTTPError as exc:
        return {"ok": False, "error": str(exc), "latency_ms": None}
    return {"ok": ok, "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}


def _check_sqlite() -> dict:
    t0 = time.perf_counter()
    try:
        conn = sqlite3.connect(config.DATABASE_PATH, timeout=2.0)
        conn.execute("SELECT 1").fetchone()
        conn.close()
    except sqlite3.Error as exc:
        return {"ok": False, "error": str(exc), "latency_ms": None}
    return {"ok": True, "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}


async def _check_mqtt() -> dict:
    import asyncio

    t0 = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(config.MQTT_BROKER_HOST, config.MQTT_BROKER_PORT),
            timeout=2.0,
        )
        writer.close()
        await writer.wait_closed()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "latency_ms": None}
    return {"ok": True, "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}


@router.get("/health/live")
async def liveness():
    
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness() -> JSONResponse:
    

    checks: dict[str, Any] = {
        "fuseki": await _check_fuseki() if config.SEMANTIC_WRITE_ENABLED else {"ok": True, "disabled": True},
        "sqlite": _check_sqlite(),
        "mqtt": await _check_mqtt(),
    }
    all_ok = all(v["ok"] for v in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"ready": all_ok, "checks": checks},
    )
