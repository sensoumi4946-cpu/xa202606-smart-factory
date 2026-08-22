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
from connectivity.binding_source import binding_source
from connectivity.router import forward_to_backend
from semantic_layer.protocol_binding import ProtocolBinding, decode_registers

RECONNECT_INTERVAL = 5.0

UNIT_BY_PROPERTY = {
    "temperature": "celsius",
    "humidity": "percent",
    "co": "ppm",
    "smoke": "ppm",
    "combustible_gas": "ppm",
    "distance": "cm",
    "count": "count",
    "occupancy": "boolean",
    "light_state": "boolean",
    "device_status": "status",
    "error_code": "status",
    "sensor_status": "status",
}


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


def unit_for(binding: ProtocolBinding) -> Optional[Unit]:
    name = binding.unit or UNIT_BY_PROPERTY.get(binding.property_name, "")
    try:
        return Unit(name)
    except ValueError:
        return None


def measurement_for(binding: ProtocolBinding, words: list[int]) -> Optional[Measurement]:
    try:
        mtype = MeasurementType(binding.property_name)
    except ValueError:
        log_json(
            "unknown_measurement_type",
            level="warning",
            device_id=binding.device_id,
            property_name=binding.property_name,
        )
        return None

    unit = unit_for(binding)
    if unit is None:
        log_json(
            "unknown_unit",
            level="warning",
            device_id=binding.device_id,
            property_name=binding.property_name,
        )
        return None

    try:
        value = decode_registers(
            words,
            register_type=binding.register_type,
            word_order=binding.word_order,
            byte_order=binding.byte_order,
            scale_factor=binding.scale_factor,
            offset=binding.offset,
        )
    except ValueError as exc:
        log_json(
            "decode_failed",
            level="warning",
            device_id=binding.device_id,
            property_name=binding.property_name,
            error=str(exc),
        )
        return None

    return Measurement(type=mtype, value=round(value, 4), unit=unit)


def decode_block(
    registers: list[int],
    start_address: int,
    entries: list[ProtocolBinding],
) -> list[UnifiedMessage]:
    grouped: dict[tuple[str, str], list[Measurement]] = {}
    consumed: dict[tuple[str, str], list[int]] = {}

    for binding in entries:
        offset = (binding.wire_address or 0) - start_address
        if offset < 0 or offset + binding.register_count > len(registers):
            continue
        words = list(registers[offset : offset + binding.register_count])
        measurement = measurement_for(binding, words)
        if measurement is None:
            continue
        key = (binding.device_id, binding.canonical_subsystem)
        grouped.setdefault(key, []).append(measurement)
        consumed.setdefault(key, []).extend(words)

    messages = []
    for (device_id, subsystem), measurements in sorted(grouped.items()):
        try:
            subsystem_enum = Subsystem(subsystem)
        except ValueError:
            log_json(
                "unknown_subsystem",
                level="warning",
                device_id=device_id,
                subsystem=subsystem,
            )
            continue
        messages.append(
            UnifiedMessage(
                schema_version="v1",
                device_id=device_id,
                subsystem=subsystem_enum,
                protocol=Protocol.MODBUS,
                measurements=measurements,
                raw_payload={
                    "registers": consumed[(device_id, subsystem)],
                    "start_address": start_address,
                },
            )
        )
    return messages


def parse_registers(
    registers: list[int],
    slave_id: int = 1,
    start_address: Optional[int] = None,
    entries: Optional[list[ProtocolBinding]] = None,
) -> list[UnifiedMessage]:
    if entries is None:
        entries = binding_source.modbus_entries(slave_id)
    if not entries:
        raise ValueError(f"no modbus bindings declared for slave {slave_id}")

    if start_address is None:
        start_address = min(b.wire_address or 0 for b in entries)

    span = max((b.wire_address or 0) + b.register_count for b in entries) - start_address
    if len(registers) < span:
        raise ValueError(
            f"slave {slave_id} needs {span} registers from {start_address}, "
            f"got {len(registers)}"
        )

    return decode_block(registers, start_address, entries)


class ModbusAdapter(BaseAdapter):
    def __init__(self, source=None):
        self.source = source or binding_source
        self.host = connectivity_models.MODBUS_HOST
        self.port = connectivity_models.MODBUS_PORT
        self._queue: Optional[asyncio.Queue[UnifiedMessage]] = None
        self._running = False

    @property
    def read_plan(self) -> list[dict[str, Any]]:
        return self.source.read_plan()

    @property
    def devices(self) -> list[str]:
        return sorted({b.device_id for b in self.source.modbus_entries()})

    async def start(self) -> None:
        self._running = True
        self._ensure_queue()

        plan = self.read_plan
        if not plan:
            log_json(
                "modbus_no_bindings",
                level="warning",
                endpoint=f"{self.host}:{self.port}",
            )
            return

        while self._running:
            client = self._make_client()
            try:
                if not await self._connect(client):
                    await asyncio.sleep(RECONNECT_INTERVAL)
                    continue
                log_json(
                    "modbus_connected",
                    endpoint=f"{self.host}:{self.port}",
                    reads=len(plan),
                    devices=self.devices,
                )
                while self._running:
                    for read in self.read_plan:
                        await self.poll_once(client, read)
                    await asyncio.sleep(self._sleep_seconds(self.read_plan))
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

    def _sleep_seconds(self, plan: list[dict[str, Any]]) -> float:
        if not plan:
            return RECONNECT_INTERVAL
        return min(read["poll_interval_ms"] for read in plan) / 1000.0

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

    async def _read(self, client: Any, read: dict[str, Any]):
        if read["function_code"] == 4:
            reader = getattr(client, "read_input_registers", None)
            if reader is not None:
                return await reader(
                    address=read["start_address"], count=read["count"]
                )
        return await client.read_holding_registers(
            address=read["start_address"], count=read["count"]
        )

    async def poll_once(
        self, client: Any, read: Optional[dict[str, Any]] = None
    ) -> list[UnifiedMessage]:
        if read is None:
            plan = self.read_plan
            if not plan:
                return []
            read = plan[0]

        result = await self._read(client, read)
        if result.isError():
            log_json(
                "modbus_read_failed",
                level="warning",
                slave_id=read["slave_id"],
                start_address=read["start_address"],
            )
            return []

        messages = decode_block(
            list(result.registers), read["start_address"], read["entries"]
        )
        queue = self._ensure_queue()
        for msg in messages:
            queue.put_nowait(msg)
            await forward_to_backend(msg)
            log_json(
                "message_parsed",
                device_id=msg.device_id,
                subsystem=msg.subsystem.value,
                measurements=len(msg.measurements),
            )
        return messages

    def _close(self, client: Any) -> None:
        close = getattr(client, "close", None)
        if close:
            close()
