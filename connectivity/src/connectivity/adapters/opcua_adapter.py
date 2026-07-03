import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import Optional

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

RECONNECT_INTERVAL = 5.0
SUB_INTERVAL_MS = 500


def log_json(event: str, level: str = "info", **kwargs):
    entry = {
        "service": "connectivity.opcua",
        "event": event,
        "level": level,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    stream = sys.stderr if level in ("error", "warning") else sys.stdout
    print(json.dumps(entry), file=stream)


def make_message_from_node(
    node_id: str, value: float, device_id: str = "sensor_hcsr04_01"
) -> UnifiedMessage:
    return UnifiedMessage(
        schema_version="v1",
        device_id=device_id,
        subsystem=Subsystem.AGV,
        protocol=Protocol.OPCUA,
        measurements=[
            Measurement(
                type=MeasurementType.DISTANCE,
                value=float(value),
                unit=Unit.CM,
            ),
        ],
        raw_payload={"node_id": node_id, "value": float(value)},
    )


class SubscriptionHandler:
    def __init__(
        self, queue: asyncio.Queue[UnifiedMessage], node_id: str, device_id: str
    ):
        self.queue = queue
        self.node_id = node_id
        self.device_id = device_id

    def datachange_notification(self, node, val, data):
        msg = make_message_from_node(self.node_id, float(val), self.device_id)
        self.queue.put_nowait(msg)


class OPCUAAdapter(BaseAdapter):
    def __init__(self):
        self.endpoint = connectivity_models.OPCUA_ENDPOINT
        self.device_id = connectivity_models.OPCUA_DEVICE_ID
        self.node_id = connectivity_models.OPCUA_DISTANCE_NODE_ID
        self._queue: Optional[asyncio.Queue[UnifiedMessage]] = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._ensure_queue()
        while self._running:
            client = self._make_client()
            sub = None
            try:
                if not await self._connect(client):
                    await asyncio.sleep(RECONNECT_INTERVAL)
                    continue
                node = client.get_node(self.node_id)
                handler = SubscriptionHandler(
                    self._ensure_queue(), self.node_id, self.device_id
                )
                sub = await client.create_subscription(SUB_INTERVAL_MS, handler)
                await sub.subscribe_data_change(node)
                log_json(
                    "opcua_subscribed", endpoint=self.endpoint, node_id=self.node_id
                )
                while self._running:
                    try:
                        await self.forward_once(timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
            except Exception as exc:
                log_json("opcua_connection_lost", level="warning", error=str(exc))
                await asyncio.sleep(RECONNECT_INTERVAL)
            finally:
                if sub:
                    await sub.delete()
                await self._disconnect(client)

    async def stop(self) -> None:
        self._running = False
        log_json("opcua_stopped")

    async def receive(self) -> UnifiedMessage:
        return await self._ensure_queue().get()

    def _ensure_queue(self) -> asyncio.Queue[UnifiedMessage]:
        if self._queue is None:
            self._queue = asyncio.Queue()
        return self._queue

    def _make_client(self):
        from asyncua import Client

        return Client(url=self.endpoint)

    async def _connect(self, client) -> bool:
        try:
            await client.connect()
            log_json("opcua_connected", endpoint=self.endpoint)
            return True
        except Exception as exc:
            log_json("opcua_connect_failed", level="warning", error=str(exc))
            return False

    async def _disconnect(self, client) -> None:
        try:
            await client.disconnect()
        except Exception as exc:
            log_json("opcua_disconnect_failed", level="warning", error=str(exc))

    async def forward_once(self, timeout: Optional[float] = None) -> UnifiedMessage:
        if timeout is None:
            msg = await self.receive()
        else:
            msg = await asyncio.wait_for(self.receive(), timeout=timeout)
        await forward_to_backend(msg)
        log_json(
            "message_parsed", device_id=msg.device_id, subsystem=msg.subsystem.value
        )
        return msg
