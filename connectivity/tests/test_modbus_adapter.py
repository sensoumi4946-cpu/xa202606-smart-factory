import asyncio

import pytest

from connectivity.adapters import modbus_adapter
from connectivity.adapters.modbus_adapter import ModbusAdapter, parse_registers


def by_type(msg, measurement_type: str):
    return {m.type.value: m for m in msg.measurements}[measurement_type]


def test_modbus_registers_parsed():
    msg = parse_registers([3, 12, 0], device_id="sensor_mq2_01")
    assert msg.schema_version == "v1"
    assert msg.device_id == "sensor_mq2_01"
    assert msg.subsystem.value == "gas"
    assert msg.protocol.value == "modbus"
    assert by_type(msg, "smoke").value == 3.0
    assert by_type(msg, "co").value == 12.0
    assert by_type(msg, "combustible_gas").value == 0.0
    assert msg.raw_payload == {"registers": [3, 12, 0], "base_address": 1}


def test_modbus_short_registers_rejected():
    with pytest.raises(ValueError):
        parse_registers([3, 12])


def test_modbus_connection_refused():
    class FakeClient:
        async def connect(self):
            return False

    adapter = ModbusAdapter()
    assert asyncio.run(adapter._connect(FakeClient())) is False


def test_modbus_forward_to_backend(monkeypatch):
    class FakeResult:
        registers = [3, 12, 0]

        def isError(self):
            return False

    class FakeClient:
        async def read_holding_registers(self, address, count):
            assert address == 1
            assert count == 3
            return FakeResult()

    captured = []

    async def fake_forward(msg):
        captured.append(msg)
        return True

    monkeypatch.setattr(modbus_adapter, "forward_to_backend", fake_forward)
    msg = asyncio.run(ModbusAdapter().poll_once(FakeClient()))
    assert msg is not None
    assert captured[0].protocol.value == "modbus"
    assert by_type(captured[0], "co").value == 12.0
