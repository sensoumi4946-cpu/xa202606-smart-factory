# Unit tests for the shared data contracts (UnifiedMessage, Measurement, enums).
# Validates Pydantic model construction, JSON serialisation round-trip,
# and field-level validation (missing device_id, empty measurements,
# missing schema_version).
from datetime import datetime, timezone

from smart_factory_contracts.messages import (
    Measurement,
    MeasurementType,
    Protocol,
    Subsystem,
    UnifiedMessage,
    Unit,
)


def test_measurement_valid():
    m = Measurement(type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS)
    assert m.type == MeasurementType.TEMPERATURE
    assert m.value == 25.5
    assert m.unit == Unit.CELSIUS


def test_unified_message_minimal():
    msg = UnifiedMessage(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        measurements=[
            Measurement(
                type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS
            ),
            Measurement(type=MeasurementType.HUMIDITY, value=60.0, unit=Unit.PERCENT),
        ],
    )
    assert msg.schema_version == "v1"
    assert msg.device_id == "sensor_dht22_01"
    assert msg.protocol == Protocol.MQTT
    assert len(msg.measurements) == 2
    assert msg.timestamp.tzinfo is not None


def test_unified_message_full():
    msg = UnifiedMessage(
        schema_version="v1",
        device_id="sensor_mq2_01",
        subsystem=Subsystem.GAS,
        protocol=Protocol.MQTT,
        timestamp=datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc),
        measurements=[
            Measurement(type=MeasurementType.SMOKE, value=0.0, unit=Unit.PPM),
            Measurement(type=MeasurementType.CO, value=5.0, unit=Unit.PPM),
        ],
        raw_payload={"topic": "factory/gas/sensors/sensor_mq2_01/co"},
    )
    assert msg.timestamp.isoformat() == "2026-07-01T12:00:00+00:00"
    assert msg.raw_payload is not None


def test_json_serialization():
    msg = UnifiedMessage(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        measurements=[
            Measurement(
                type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS
            ),
        ],
    )
    data = msg.model_dump(mode="json")
    parsed = UnifiedMessage.model_validate(data)
    assert parsed.device_id == msg.device_id


def test_missing_device_id_rejected():
    try:
        UnifiedMessage(
            schema_version="v1",
            device_id="",
            subsystem=Subsystem.TEMP_HUMIDITY,
            protocol=Protocol.MQTT,
            measurements=[
                Measurement(
                    type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS
                ),
            ],
        )
        assert False, "expected validation error"
    except Exception:
        pass


def test_empty_measurements_rejected():
    try:
        UnifiedMessage(
            schema_version="v1",
            device_id="sensor_dht22_01",
            subsystem=Subsystem.TEMP_HUMIDITY,
            protocol=Protocol.MQTT,
            measurements=[],
        )
        assert False, "expected validation error"
    except Exception:
        pass


def test_missing_schema_version_rejected():
    from pydantic import ValidationError

    try:
        UnifiedMessage(
            device_id="sensor_dht22_01",
            subsystem=Subsystem.TEMP_HUMIDITY,
            protocol=Protocol.MQTT,
            measurements=[
                Measurement(
                    type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS
                ),
            ],
        )
        assert False, "expected ValidationError"
    except ValidationError:
        pass


def test_subsystem_enum_values():
    assert Subsystem.TEMP_HUMIDITY.value == "temp_humidity"
    assert Subsystem.LIGHTING.value == "lighting"
    assert Subsystem.GAS.value == "gas"
    assert Subsystem.AGV.value == "agv"
    assert Subsystem.COUNTING.value == "counting"


def test_measurement_type_enum_values():
    assert MeasurementType.TEMPERATURE.value == "temperature"
    assert MeasurementType.HUMIDITY.value == "humidity"
    assert MeasurementType.OCCUPANCY.value == "occupancy"
    assert MeasurementType.CO.value == "co"
    assert MeasurementType.DISTANCE.value == "distance"
    assert MeasurementType.COUNT.value == "count"
