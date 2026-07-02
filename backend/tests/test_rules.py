# Unit + integration tests for the rules engine.
import pytest
from smart_factory_contracts.messages import (
    Measurement,
    MeasurementType,
    Protocol,
    Subsystem,
    UnifiedMessage,
    Unit,
)

from backend.store import init_db, insert_sensor_data, query_alerts


@pytest.fixture(autouse=True)
def _init_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("backend.store.DATABASE_PATH", str(db_path))
    monkeypatch.setattr("backend.config.DATABASE_PATH", str(db_path))
    init_db()


@pytest.mark.asyncio
async def test_high_temp_triggers_alert():
    msg = UnifiedMessage(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        measurements=[
            Measurement(
                type=MeasurementType.TEMPERATURE, value=39.0, unit=Unit.CELSIUS
            ),
        ],
    )
    insert_sensor_data(msg)
    result = query_alerts()
    assert result["total"] == 1
    a = result["items"][0]
    assert a["rule_name"] == "high_temp"
    assert a["level"] == "warning"
    assert a["value"] == 39.0
    assert a["threshold"] == 38


@pytest.mark.asyncio
async def test_normal_temp_no_alert():
    msg = UnifiedMessage(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        measurements=[
            Measurement(
                type=MeasurementType.TEMPERATURE, value=25.0, unit=Unit.CELSIUS
            ),
        ],
    )
    insert_sensor_data(msg)
    result = query_alerts()
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_multiple_measurements_multi_alerts():
    msg = UnifiedMessage(
        schema_version="v1",
        device_id="sensor_mq2_01",
        subsystem=Subsystem.GAS,
        protocol=Protocol.MQTT,
        measurements=[
            Measurement(
                type=MeasurementType.TEMPERATURE, value=39.0, unit=Unit.CELSIUS
            ),
            Measurement(type=MeasurementType.CO, value=40.0, unit=Unit.PPM),
        ],
    )
    insert_sensor_data(msg)
    result = query_alerts()
    assert result["total"] == 2
    rule_names = {a["rule_name"] for a in result["items"]}
    assert "high_temp" in rule_names
    assert "co_warning" in rule_names


@pytest.mark.asyncio
async def test_alert_dedup_in_window():
    m = Measurement(type=MeasurementType.TEMPERATURE, value=39.0, unit=Unit.CELSIUS)
    msg = UnifiedMessage(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        measurements=[m.model_copy()],
    )
    insert_sensor_data(msg)
    insert_sensor_data(msg)
    result = query_alerts()
    assert result["total"] == 1
