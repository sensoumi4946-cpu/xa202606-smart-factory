import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional

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
from connectivity.generated_adapters import GeneratedAdapterSet, load_adapter_set
from connectivity.models import MQTT_BROKER_HOST, MQTT_BROKER_PORT
from connectivity.router import forward_to_backend

SENSOR_TOPIC = os.getenv("MQTT_SENSOR_TOPIC", "factory/+/sensors/#")


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
    def __init__(self, bindings: GeneratedAdapterSet | None = None):
        self.bindings = bindings or load_adapter_set()
        self._client: Optional[Any] = None
        self._queue: asyncio.Queue[UnifiedMessage] = asyncio.Queue()
        self._running = False

    async def start(self) -> None:
        import paho.mqtt.client as mqtt

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
            subscriptions = self.bindings.mqtt_subscriptions()
            if subscriptions:
                for topic, qos in subscriptions:
                    client.subscribe(topic, qos=qos)
                    log_json("mqtt_subscribed", topic=topic, qos=qos)
            else:
                client.subscribe(SENSOR_TOPIC)
                log_json("mqtt_subscribed", topic=SENSOR_TOPIC)
        else:
            log_json("mqtt_connect_failed", level="error", reason_code=str(reason_code))

    def _on_message(self, client, userdata, msg):
        binding = self.bindings.mqtt_entry(msg.topic)
        parts = msg.topic.split("/")
        device_id = (
            binding["device_id"]
            if binding
            else (parts[3] if len(parts) > 3 else "unknown")
        )
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
        binding = self.bindings.mqtt_entry(topic)
        if "control" in parts or (binding is None and len(parts) < 4):
            return None
        subsystem = binding["subsystem"] if binding else parts[1]
        device_id = binding["device_id"] if binding else parts[3]

        measurements: list[Measurement] = []
        mdata = raw if isinstance(raw, dict) else {"value": raw}
        mtype_val = (
            binding["property_name"]
            if binding
            else mdata.get("type", parts[-1] if len(parts) > 4 else "unknown")
        )
        raw_value = float(mdata.get("value", 0))
        mvalue = (
            raw_value * binding["scale_factor"] + binding["offset"]
            if binding
            else raw_value
        )
        munit = binding["unit"] if binding else mdata.get("unit", "count")
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
