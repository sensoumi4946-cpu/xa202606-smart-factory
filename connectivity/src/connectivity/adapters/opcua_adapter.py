

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import connectivity.models as connectivity_models
from connectivity.adapters.base import BaseAdapter
from connectivity.generated_adapters import GeneratedAdapterSet, load_adapter_set
from connectivity.router import forward_to_backend
from smart_factory_contracts.messages import UnifiedMessage


def log_json(event: str, level: str = "info", **kwargs: Any) -> None:
    entry = {
        "service": "connectivity.opcua",
        "event": event,
        "level": level,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    stream = sys.stderr if level in ("error", "warning") else sys.stdout
    print(json.dumps(entry), file=stream)


def _node_id(node: Any) -> str:
    identifier = getattr(node, "nodeid", node)
    to_string = getattr(identifier, "to_string", None)
    return to_string() if callable(to_string) else str(identifier)


def make_message_from_node(
    node_id: str,
    value: float,
    bindings: GeneratedAdapterSet | None = None,
) -> UnifiedMessage:
    adapter_set = bindings or load_adapter_set()
    payload = adapter_set.message_from_opcua(node_id, value)
    if payload is None:
        raise ValueError(f"OPC UA node {node_id!r} has no protocol binding")
    return UnifiedMessage.model_validate(payload)


class SubscriptionHandler:
    def __init__(
        self,
        queue: asyncio.Queue[UnifiedMessage],
        bindings: GeneratedAdapterSet,
    ) -> None:
        self.queue = queue
        self.bindings = bindings

    def datachange_notification(self, node, val, data) -> None:
        node_id = _node_id(node)
        try:
            message = make_message_from_node(node_id, float(val), self.bindings)
        except (TypeError, ValueError) as exc:
            log_json(
                "opcua_value_rejected",
                level="warning",
                node_id=node_id,
                error=str(exc),
            )
            return
        if self.queue.full():
            log_json("opcua_queue_overflow", level="error", device_id=message.device_id)
            return
        self.queue.put_nowait(message)


class OPCUAAdapter(BaseAdapter):
    def __init__(self, bindings: GeneratedAdapterSet | None = None) -> None:
        self.endpoint = connectivity_models.OPCUA_ENDPOINT
        self.bindings = bindings or load_adapter_set()
        self._queue: asyncio.Queue[UnifiedMessage] | None = None
        self._running = False

    async def start(self) -> None:
        nodes = self.bindings.opcua_nodes()
        if not nodes:
            raise RuntimeError("no valid OPC UA bindings are configured")

        self._running = True
        self._ensure_queue()
        while self._running:
            client = self._make_client()
            subscription = None
            try:
                await self._configure_client(client)
                if not await self._connect(client):
                    await asyncio.sleep(connectivity_models.RECONNECT_INTERVAL)
                    continue
                interval = min(node["poll_interval_ms"] for node in nodes)
                handler = SubscriptionHandler(self._ensure_queue(), self.bindings)
                subscription = await client.create_subscription(interval, handler)
                for entry in nodes:
                    await subscription.subscribe_data_change(
                        client.get_node(entry["node_id"])
                    )
                log_json(
                    "opcua_subscribed",
                    endpoint=self.endpoint,
                    node_count=len(nodes),
                )
                while self._running:
                    try:
                        await self.forward_once(timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
            except Exception as exc:
                log_json("opcua_connection_lost", level="warning", error=str(exc))
                await asyncio.sleep(connectivity_models.RECONNECT_INTERVAL)
            finally:
                try:
                    if subscription:
                        await subscription.delete()
                except Exception as exc:
                    log_json("opcua_cleanup_failed", level="warning", error=str(exc))
                finally:
                    await self._disconnect(client)

    async def stop(self) -> None:
        self._running = False
        log_json("opcua_stopped")

    async def receive(self) -> UnifiedMessage:
        return await self._ensure_queue().get()

    def _ensure_queue(self) -> asyncio.Queue[UnifiedMessage]:
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=4096)
        return self._queue

    def _make_client(self):
        from asyncua import Client

        return Client(url=self.endpoint)

    async def _configure_client(self, client) -> None:
        pass
        if connectivity_models.OPCUA_USERNAME:
            client.set_user(connectivity_models.OPCUA_USERNAME)
        if connectivity_models.OPCUA_PASSWORD:
            client.set_password(connectivity_models.OPCUA_PASSWORD)
        if connectivity_models.OPCUA_SECURITY_STRING:
            await client.set_security_string(
                connectivity_models.OPCUA_SECURITY_STRING
            )
        user_cert = connectivity_models.OPCUA_USER_CERTIFICATE
        user_key = connectivity_models.OPCUA_USER_PRIVATE_KEY
        if bool(user_cert) != bool(user_key):
            raise ValueError(
                "OPCUA_USER_CERTIFICATE and OPCUA_USER_PRIVATE_KEY must be set together"
            )
        if user_cert:
            await client.load_client_certificate(user_cert)
            await client.load_private_key(
                Path(user_key),
                password=(
                    connectivity_models.OPCUA_USER_PRIVATE_KEY_PASSWORD or None
                ),
            )

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

    async def forward_once(self, timeout: float | None = None) -> UnifiedMessage:
        if timeout is None:
            message = await self.receive()
        else:
            message = await asyncio.wait_for(self.receive(), timeout=timeout)
        await forward_to_backend(message)
        log_json(
            "message_parsed",
            device_id=message.device_id,
            subsystem=message.subsystem.value,
        )
        return message
