# Unit tests for the mock data generator.
# Verifies all five subsystems produce valid UnifiedMessages with
# physically-plausible values (temperature 15-40°C, humidity 20-90%,
# distance 10-400cm, count 0-200).
import pytest
from smart_factory_contracts.messages import MeasurementType, Subsystem, Unit

from analytics.mock.generator import SUBSYSTEM_DEVICES, generate_message


def test_generate_temp_humidity():
    msg = generate_message("sensor_dht22_01", Subsystem.TEMP_HUMIDITY)
    assert msg.device_id == "sensor_dht22_01"
    assert msg.subsystem == Subsystem.TEMP_HUMIDITY
    assert msg.protocol.value == "mock"
    assert len(msg.measurements) == 2
    types = [m.type for m in msg.measurements]
    assert MeasurementType.TEMPERATURE in types
    assert MeasurementType.HUMIDITY in types


def test_generate_lighting():
    msg = generate_message("sensor_pir_01", Subsystem.LIGHTING)
    assert msg.subsystem == Subsystem.LIGHTING
    assert len(msg.measurements) == 2
    types = [m.type for m in msg.measurements]
    assert MeasurementType.OCCUPANCY in types
    assert MeasurementType.LIGHT_STATE in types


def test_generate_gas():
    msg = generate_message("sensor_mq2_01", Subsystem.GAS)
    assert msg.subsystem == Subsystem.GAS
    assert len(msg.measurements) == 3
    types = [m.type for m in msg.measurements]
    assert MeasurementType.SMOKE in types
    assert MeasurementType.CO in types
    assert MeasurementType.COMBUSTIBLE_GAS in types


def test_generate_agv():
    msg = generate_message("sensor_hcsr04_01", Subsystem.AGV)
    assert msg.subsystem == Subsystem.AGV
    assert len(msg.measurements) == 1
    assert msg.measurements[0].type == MeasurementType.DISTANCE
    assert 10.0 <= msg.measurements[0].value <= 400.0
    assert msg.measurements[0].unit == Unit.CM


def test_generate_counting():
    msg = generate_message("sensor_ir_01", Subsystem.COUNTING)
    assert msg.subsystem == Subsystem.COUNTING
    assert len(msg.measurements) == 1
    assert msg.measurements[0].type == MeasurementType.COUNT
    assert 0.0 <= msg.measurements[0].value <= 200.0
    assert msg.measurements[0].unit == Unit.COUNT


def test_all_subsystems_covered():
    for subsystem in Subsystem:
        device_id = SUBSYSTEM_DEVICES[subsystem][0]
        msg = generate_message(device_id, subsystem)
        assert msg is not None
        assert msg.device_id == device_id
        assert len(msg.measurements) > 0
        assert msg.timestamp.tzinfo is not None


def test_temperature_in_valid_range():
    for _ in range(20):
        msg = generate_message("sensor_dht22_01", Subsystem.TEMP_HUMIDITY)
        temp = [m for m in msg.measurements if m.type == MeasurementType.TEMPERATURE][0]
        assert 15.0 <= temp.value <= 40.0


def test_humidity_in_valid_range():
    for _ in range(20):
        msg = generate_message("sensor_dht22_01", Subsystem.TEMP_HUMIDITY)
        hum = [m for m in msg.measurements if m.type == MeasurementType.HUMIDITY][0]
        assert 20.0 <= hum.value <= 90.0
