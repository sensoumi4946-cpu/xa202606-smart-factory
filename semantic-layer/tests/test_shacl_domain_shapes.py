# Regression tests for observation_gate.check_and_prepare() against
# shacl_domain_shapes.py.

from datetime import datetime, timezone

import pytest

from semantic_layer.observation_gate import check_and_prepare
from smart_factory_contracts.messages import (
    Measurement, MeasurementType, Protocol, Subsystem, Unit, UnifiedMessage,
)


def _msg(device_id, subsystem, mtype, value, unit, protocol=Protocol.MQTT):
    return UnifiedMessage(
        schema_version="v1",
        device_id=device_id,
        subsystem=subsystem,
        protocol=protocol,
        timestamp=datetime.now(timezone.utc),
        measurements=[Measurement(type=mtype, value=value, unit=unit)],
    )


# One valid case per subsystem — these are the exact shapes of message
# each real adapter (MQTT/Modbus/OPC UA/REST) sends. Every one of these
# must be accepted or real sensor data will silently stop reaching Fuseki.

@pytest.mark.parametrize(
    "device_id,subsystem,mtype,value,unit,protocol",
    [
        ("sensor_dht22_01", Subsystem.TEMP_HUMIDITY, MeasurementType.TEMPERATURE, 25.5, Unit.CELSIUS, Protocol.MQTT),
        ("sensor_dht22_01", Subsystem.TEMP_HUMIDITY, MeasurementType.HUMIDITY, 60.0, Unit.PERCENT, Protocol.MQTT),
        ("sensor_mq2_01", Subsystem.GAS, MeasurementType.CO, 5.0, Unit.PPM, Protocol.MODBUS),
        ("sensor_mq2_01", Subsystem.GAS, MeasurementType.SMOKE, 5.0, Unit.PPM, Protocol.MODBUS),
        ("sensor_mq2_01", Subsystem.GAS, MeasurementType.COMBUSTIBLE_GAS, 5.0, Unit.PPM, Protocol.MODBUS),
        ("sensor_agv_01", Subsystem.AGV, MeasurementType.DISTANCE, 80.0, Unit.CM, Protocol.OPCUA),
        ("sensor_ir_01", Subsystem.COUNTING, MeasurementType.COUNT, 3.0, Unit.COUNT, Protocol.REST),
        ("sensor_pir_01", Subsystem.LIGHTING, MeasurementType.OCCUPANCY, 1.0, Unit.BOOLEAN, Protocol.REST),
        ("sensor_pir_01", Subsystem.LIGHTING, MeasurementType.LIGHT_STATE, 0.0, Unit.BOOLEAN, Protocol.REST),
    ],
)
def test_valid_reading_accepted_for_every_subsystem(device_id, subsystem, mtype, value, unit, protocol):
    msg = _msg(device_id, subsystem, mtype, value, unit, protocol)
    gate = check_and_prepare(msg)
    assert gate.accepted, f"{mtype} should be accepted, got violations: {gate.report.violations}"
    assert gate.report.violations == []


# Genuinely bad readings must still be rejected — the fix must not
# accidentally turn the gate into a rubber stamp.

@pytest.mark.parametrize(
    "device_id,subsystem,mtype,value,unit",
    [
        ("sensor_dht22_01", Subsystem.TEMP_HUMIDITY, MeasurementType.TEMPERATURE, 999.0, Unit.CELSIUS),   # out of range
        ("sensor_dht22_01", Subsystem.TEMP_HUMIDITY, MeasurementType.HUMIDITY, 150.0, Unit.PERCENT),      # out of range
        ("sensor_mq2_01", Subsystem.GAS, MeasurementType.CO, 99999.0, Unit.PPM),                          # out of range
        ("sensor_agv_01", Subsystem.AGV, MeasurementType.DISTANCE, -5.0, Unit.CM),                        # negative
        ("sensor_ir_01", Subsystem.COUNTING, MeasurementType.COUNT, -1.0, Unit.COUNT),                    # negative
    ],
)
def test_invalid_reading_rejected(device_id, subsystem, mtype, value, unit):
    msg = _msg(device_id, subsystem, mtype, value, unit)
    gate = check_and_prepare(msg)
    assert not gate.accepted
    assert gate.report.violations != []


def test_warning_only_shapes_do_not_block_ingestion():
    """
    SensorSubsystemShape and QUDTEnrichmentShape are sh:Warning severity
    by design (they should nudge, not block). A previously-real bug made
    pyshacl's raw `conforms` flag go False on Warning-only results too,
    which would have 422-rejected perfectly valid data. This test pins
    that a normal valid message is accepted even though warning shapes
    exist in the shape graph.
    """
    msg = _msg("sensor_dht22_01", Subsystem.TEMP_HUMIDITY, MeasurementType.TEMPERATURE, 25.0, Unit.CELSIUS)
    gate = check_and_prepare(msg)
    assert gate.accepted
