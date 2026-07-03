import pytest

from connectivity.adapters.modbus_adapter import parse_registers


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
    assert msg.raw_payload == {"registers": [3, 12, 0], "base_address": 0}


def test_modbus_short_registers_rejected():
    with pytest.raises(ValueError):
        parse_registers([3, 12])
