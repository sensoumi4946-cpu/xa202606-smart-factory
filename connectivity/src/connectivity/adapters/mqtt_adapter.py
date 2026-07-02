# MQTT protocol adapter — the only fully implemented adapter in Phase 1.
#
# Subscribes to factory/+/sensors/# (wildcard for all subsystems, all
# devices, all measurement types), parses each payload into a
# UnifiedMessage, and pushes it through the router to the backend.
#
# Topic structure: factory/{subsystem}/sensors/{device_id}/{measurement_type}
# Control topics (factory/*/control/...) are explicitly filtered out
# so they never enter the sensor data pipeline.
import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import Optional

import paho.mqtt.client as mqtt
from pydantic import ValidationError
from smart_factory_contracts.messages import (
    Measurement,
    MeasurementType,
    Protocol,
    Subsystem,
    UnifiedMessage,
    Unit,
)

from connectivity.adapters.base import BaseAdapter
from connectivity.models import MQTT_BROKER_HOST, MQTT_BROKER_PORT
from connectivity.router import forward_to_backend

SENSOR_TOPIC = "factory/+/sensors/#"


def log_json(event: str, level: str = "info", **kwargs):
    entry = {
        "service": "connectivity.mqtt",
        "event": event,
        "level": level,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    print(json.dumps(entry), file=sys.stderr if level == "error" else sys.stdout)


class MQTTAdapter(BaseAdapter):
    def __init__(self):
        self._client: Optional[mqtt.Client] = None
        self._queue: asyncio.Queue[UnifiedMessage] = asyncio.Queue()
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

        self._client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=60)
        self._client.loop_start()
        log_json("mqtt_started", broker=f"{MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")

        while self._running:
            try:
                msg = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await forward_to_backend(msg)
            except asyncio.TimeoutError:
                continue

    async def stop(self) -> None:
        self._running = False
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
        log_json("mqtt_stopped")

    async def receive(self) -> UnifiedMessage:
        return await self._queue.get()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe(SENSOR_TOPIC)
            log_json("mqtt_subscribed", topic=SENSOR_TOPIC)
        else:
            log_json("mqtt_connect_failed", level="error", reason_code=str(reason_code))

    def _on_message(self, client, userdata, msg):
        device_id = msg.topic.split("/")[3]
        try:
            parsed = self._parse_payload(msg.topic, msg.payload.decode("utf-8"))
            if parsed is not None:
                self._queue.put_nowait(parsed)
        except ValidationError:
            log_json(
                "payload_validation_failed",
                level="warning",
                device_id=device_id,
                topic=msg.topic,
            )
        except Exception:
            log_json(
                "payload_parse_error",
                level="warning",
                device_id=device_id,
                topic=msg.topic,
            )

    def _parse_payload(self, topic: str, payload_str: str) -> Optional[UnifiedMessage]:
        raw = json.loads(payload_str)
        parts = topic.split("/")
        # Guard: skip control topics so they don't enter the sensor data pipeline
        if len(parts) < 4 or "control" in topic:
            return None

        # Derive subsystem and device_id from MQTT topic hierarchy
        subsystem = parts[1]
        device_id = parts[3]

        measurements: list[Measurement] = []
        mdata = raw if isinstance(raw, dict) else {"value": raw}
        mtype_val = mdata.get("type", parts[-1] if len(parts) > 4 else "unknown")
        mvalue = float(mdata.get("value", 0))
        munit = mdata.get("unit", "count")

        try:
            mtype = MeasurementType(mtype_val)
            unit = Unit(munit)
        except ValueError:
            log_json(
                "unknown_measurement_type",
                level="warning",
                device_id=device_id,
                raw_type=mtype_val,
            )
            return None

        measurements.append(Measurement(type=mtype, value=mvalue, unit=unit))

        msg = UnifiedMessage(
            schema_version="v1",
            device_id=device_id,
            subsystem=Subsystem(subsystem),
            protocol=Protocol.MQTT,
            measurements=measurements,
            raw_payload={"topic": topic, "payload": raw},
        )
        log_json(
            "message_parsed",
            device_id=device_id,
            subsystem=subsystem,
            measurement_type=mtype_val,
        )
        return msg
