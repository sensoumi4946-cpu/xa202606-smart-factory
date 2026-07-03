import json
import sys
from datetime import datetime, timezone
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from smart_factory_contracts.messages import (
    Measurement,
    MeasurementType,
    Protocol,
    Subsystem,
    UnifiedMessage,
    Unit,
)

import connectivity.models as connectivity_models
from connectivity.adapters.base import BaseAdapter
from connectivity.router import forward_to_backend

LIGHTING_MAP = {
    "occupancy": {"active": 1.0, "inactive": 0.0},
    "light": {"on": 1.0, "off": 0.0},
}


def log_json(event: str, level: str = "info", **kwargs):
    entry = {
        "service": "connectivity.rest",
        "event": event,
        "level": level,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    print(json.dumps(entry), file=sys.stderr if level == "error" else sys.stdout)


def parse_payload(payload: dict[str, Any]) -> UnifiedMessage:
    if not isinstance(payload, dict):
        raise ValueError("unknown payload format")

    is_lighting = "device" in payload and "metrics" in payload
    is_counting = "d" in payload and "v" in payload
    if is_lighting and is_counting:
        raise ValueError("ambiguous payload")
    if is_lighting:
        return _parse_lighting(payload)
    if is_counting:
        return _parse_counting(payload)
    raise ValueError("unknown payload format")


def _parse_lighting(payload: dict[str, Any]) -> UnifiedMessage:
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("invalid lighting payload")

    try:
        occupancy = LIGHTING_MAP["occupancy"][metrics["occupancy"]]
        light = LIGHTING_MAP["light"][metrics["light"]]
    except KeyError as exc:
        raise ValueError("invalid lighting payload") from exc

    return UnifiedMessage(
        schema_version="v1",
        device_id=str(payload["device"]),
        subsystem=Subsystem.LIGHTING,
        protocol=Protocol.REST,
        measurements=[
            Measurement(
                type=MeasurementType.OCCUPANCY,
                value=occupancy,
                unit=Unit.BOOLEAN,
            ),
            Measurement(
                type=MeasurementType.LIGHT_STATE,
                value=light,
                unit=Unit.BOOLEAN,
            ),
        ],
        raw_payload=payload,
    )


def _parse_counting(payload: dict[str, Any]) -> UnifiedMessage:
    try:
        count = float(payload["v"])
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid counting payload") from exc

    return UnifiedMessage(
        schema_version="v1",
        device_id=str(payload["d"]),
        subsystem=Subsystem.COUNTING,
        protocol=Protocol.REST,
        measurements=[
            Measurement(type=MeasurementType.COUNT, value=count, unit=Unit.COUNT),
        ],
        raw_payload=payload,
    )


def create_app() -> FastAPI:
    app = FastAPI(title="XA-202606 REST Adapter")

    @app.post("/adapter/rest/ingest")
    async def ingest(request: Request):
        try:
            payload = await request.json()
            msg = parse_payload(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail="invalid payload") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid json") from exc

        log_json(
            "message_parsed", device_id=msg.device_id, subsystem=msg.subsystem.value
        )
        if not await forward_to_backend(msg):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="backend forward failed",
            )
        return JSONResponse(status_code=202, content={"status": "accepted"})

    return app


class RESTAdapter(BaseAdapter):
    def __init__(self):
        self._server: Optional[uvicorn.Server] = None

    async def start(self) -> None:
        config = uvicorn.Config(
            create_app(),
            host="0.0.0.0",
            port=connectivity_models.REST_ADAPTER_PORT,
            log_level="info",
        )
        self._server = uvicorn.Server(config)
        log_json("rest_started", port=connectivity_models.REST_ADAPTER_PORT)
        await self._server.serve()

    async def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
        log_json("rest_stopped")

    async def receive(self) -> UnifiedMessage:
        raise NotImplementedError("REST adapter is request-driven")
