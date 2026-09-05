

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from typing import Any

import connectivity.models as connectivity_models
from connectivity.adapters.base import BaseAdapter
from connectivity.generated_adapters import GeneratedAdapterSet, load_adapter_set
from connectivity.router import forward_to_backend
from smart_factory_contracts.messages import UnifiedMessage

_READ_METHODS = {
    1: "read_coils",
    2: "read_discrete_inputs",
    3: "read_holding_registers",
    4: "read_input_registers",
}


def log_json(event: str, level: str = "info", **kwargs: Any) -> None:
    entry = {
        "service": "connectivity.modbus",
        "event": event,
        "level": level,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    stream = sys.stderr if level in ("error", "warning") else sys.stdout
    print(json.dumps(entry), file=stream)


class ModbusAdapter(BaseAdapter):
    def __init__(self, bindings: GeneratedAdapterSet | None = None) -> None:
        self.host = connectivity_models.MODBUS_HOST
        self.port = connectivity_models.MODBUS_PORT
        self.bindings = bindings or load_adapter_set()
        self._queue: asyncio.Queue[UnifiedMessage] | None = None
        self._running = False

    async def start(self) -> None:
        plans = self.bindings.modbus_read_plans()
        if not plans:
            raise RuntimeError("no valid Modbus bindings are configured")

        self._running = True
        self._ensure_queue()
        next_due = {self._plan_key(plan): 0.0 for plan in plans}
        while self._running:
            client = self._make_client()
            try:
                if not await self._connect(client):
                    await asyncio.sleep(connectivity_models.RECONNECT_INTERVAL)
                    continue
                log_json("modbus_connected", endpoint=f"{self.host}:{self.port}")
                while self._running:
                    now = time.monotonic()
                    due = [
                        plan for plan in plans if now >= next_due[self._plan_key(plan)]
                    ]
                    if due:
                        await self.poll_once(client, due)
                        for plan in due:
                            next_due[self._plan_key(plan)] = (
                                now + plan["poll_interval_ms"] / 1000.0
                            )
                    sleep_for = min(next_due.values()) - time.monotonic()
                    await asyncio.sleep(max(0.01, sleep_for))
            except Exception as exc:
                log_json("modbus_connection_lost", level="warning", error=str(exc))
                await asyncio.sleep(connectivity_models.RECONNECT_INTERVAL)
            finally:
                self._close(client)

    async def stop(self) -> None:
        self._running = False
        log_json("modbus_stopped")

    async def receive(self) -> UnifiedMessage:
        return await self._ensure_queue().get()

    def _ensure_queue(self) -> asyncio.Queue[UnifiedMessage]:
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=1)
        return self._queue

    @staticmethod
    def _plan_key(plan: dict[str, Any]) -> tuple[int, int, int, int]:
        return (
            plan["slave_id"],
            plan["function_code"],
            plan["poll_interval_ms"],
            plan["address"],
        )

    def _make_client(self):
        from pymodbus.client import AsyncModbusTcpClient

        return AsyncModbusTcpClient(self.host, port=self.port)

    async def _connect(self, client: Any) -> bool:
        connected = await client.connect()
        if not connected:
            log_json(
                "modbus_connect_failed",
                level="warning",
                endpoint=f"{self.host}:{self.port}",
            )
        return bool(connected)

    async def _read_plan(self, client: Any, plan: dict[str, Any]):
        method_name = _READ_METHODS.get(plan["function_code"])
        if method_name is None:
            raise ValueError(
                f"unsupported Modbus function code {plan['function_code']}"
            )
        method = getattr(client, method_name)
        kwargs = {"address": plan["address"], "count": plan["count"]}
        try:
            return await method(**kwargs, device_id=plan["slave_id"])
        except TypeError:
            try:
                return await method(**kwargs, slave=plan["slave_id"])
            except TypeError:
                return await method(**kwargs)

    async def poll_once(
        self, client: Any, plans: list[dict[str, Any]] | None = None
    ) -> UnifiedMessage | None:
        emitted: list[UnifiedMessage] = []
        for plan in plans or self.bindings.modbus_read_plans():
            result = await self._read_plan(client, plan)
            if result.isError():
                log_json(
                    "modbus_read_failed",
                    level="warning",
                    slave_id=plan["slave_id"],
                    function_code=plan["function_code"],
                )
                continue
            raw_values = getattr(result, "registers", None)
            if raw_values is None:
                raw_values = [int(value) for value in getattr(result, "bits", [])]

            payloads = self.bindings.messages_from_modbus_block(
                plan["slave_id"],
                list(raw_values),
                plan["address"],
                plan["function_code"],
            )
            for payload in payloads:
                message = UnifiedMessage.model_validate(payload)
                queue = self._ensure_queue()
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(message)
                await forward_to_backend(message)
                emitted.append(message)
                log_json(
                    "message_parsed",
                    device_id=message.device_id,
                    subsystem=message.subsystem.value,
                    measurement_count=len(message.measurements),
                )
        return emitted[0] if emitted else None

    def _close(self, client: Any) -> None:
        close = getattr(client, "close", None)
        if close:
            close()
