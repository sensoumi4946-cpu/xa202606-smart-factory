import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import Any, Optional

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

REGISTER_BASE = 1
REGISTER_COUNT = 3
RECONNECT_INTERVAL = 5.0


def log_json(event: str, level: str = "info", **kwargs):
    entry = {
        "service": "connectivity.modbus",
        "event": event,
        "level": level,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    stream = sys.stderr if level in ("error", "warning") else sys.stdout
    print(json.dumps(entry), file=stream)


def parse_registers(
    registers: list[int], device_id: str = "sensor_mq2_01"
) -> UnifiedMessage:
    if len(registers) < REGISTER_COUNT:
        raise ValueError("expected at least three holding registers")

    return UnifiedMessage(
        schema_version="v1",
        device_id=device_id,
        subsystem=Subsystem.GAS,
        protocol=Protocol.MODBUS,
        measurements=[
            Measurement(
                type=MeasurementType.SMOKE,
                value=float(registers[0]),
                unit=Unit.PPM,
            ),
            Measurement(
                type=MeasurementType.CO,
                value=float(registers[1]),
                unit=Unit.PPM,
            ),
            Measurement(
                type=MeasurementType.COMBUSTIBLE_GAS,
                value=float(registers[2]),
                unit=Unit.PPM,
            ),
        ],
        raw_payload={
            "registers": list(registers[:REGISTER_COUNT]),
            "base_address": REGISTER_BASE,
        },
    )


class ModbusAdapter(BaseAdapter):
    def __init__(self):
        self.host = connectivity_models.MODBUS_HOST
        self.port = connectivity_models.MODBUS_PORT
        self.device_id = connectivity_models.MODBUS_DEVICE_ID
        self.poll_interval = connectivity_models.MODBUS_POLL_INTERVAL
        self._queue: Optional[asyncio.Queue[UnifiedMessage]] = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._ensure_queue()
        while self._running:
            client = self._make_client()
            try:
                if not await self._connect(client):
                    await asyncio.sleep(RECONNECT_INTERVAL)
                    continue
                log_json("modbus_connected", endpoint=f"{self.host}:{self.port}")
                while self._running:
                    await self.poll_once(client)
                    await asyncio.sleep(self.poll_interval)
            except Exception as exc:
                log_json("modbus_connection_lost", level="warning", error=str(exc))
                await asyncio.sleep(RECONNECT_INTERVAL)
            finally:
                self._close(client)

    async def stop(self) -> None:
        self._running = False
        log_json("modbus_stopped")

    async def receive(self) -> UnifiedMessage:
        return await self._ensure_queue().get()

    def _ensure_queue(self) -> asyncio.Queue[UnifiedMessage]:
        if self._queue is None:
            self._queue = asyncio.Queue()
        return self._queue

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

    async def poll_once(self, client: Any) -> Optional[UnifiedMessage]:
        result = await client.read_holding_registers(
            address=REGISTER_BASE, count=REGISTER_COUNT
        )
        if result.isError():
            log_json("modbus_read_failed", level="warning", device_id=self.device_id)
            return None

        msg = parse_registers(result.registers, device_id=self.device_id)
        self._ensure_queue().put_nowait(msg)
        await forward_to_backend(msg)
        log_json(
            "message_parsed", device_id=msg.device_id, subsystem=msg.subsystem.value
        )
        return msg

    def _close(self, client: Any) -> None:
        close = getattr(client, "close", None)
        if close:
            close()
