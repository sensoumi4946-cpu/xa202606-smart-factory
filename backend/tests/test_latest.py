# Integration tests for GET /api/v1/latest.
import pytest
from httpx import ASGITransport, AsyncClient
from smart_factory_contracts.messages import (
    Measurement,
    MeasurementType,
    Protocol,
    Subsystem,
    UnifiedMessage,
    Unit,
)

from backend.main import app
from backend.store import init_db


@pytest.fixture(autouse=True)
def _init_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("backend.store.DATABASE_PATH", str(db_path))
    monkeypatch.setattr("backend.config.DATABASE_PATH", str(db_path))
    monkeypatch.setattr("backend.config.LATEST_WINDOW_MINUTES", 999999)
    monkeypatch.setattr("backend.store.LATEST_WINDOW_MINUTES", 999999)
    init_db()


@pytest.mark.asyncio
async def test_latest_aggregates():
    from datetime import datetime, timezone

    msg1 = UnifiedMessage(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        timestamp=datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc),
        measurements=[
            Measurement(
                type=MeasurementType.TEMPERATURE, value=22.0, unit=Unit.CELSIUS
            ),
        ],
    )
    msg2 = UnifiedMessage(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        timestamp=datetime(2026, 7, 1, 10, 1, 0, tzinfo=timezone.utc),
        measurements=[
            Measurement(
                type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS
            ),
        ],
    )
    msg3 = UnifiedMessage(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        timestamp=datetime(2026, 7, 1, 10, 2, 0, tzinfo=timezone.utc),
        measurements=[
            Measurement(type=MeasurementType.HUMIDITY, value=62.1, unit=Unit.PERCENT),
        ],
    )

    from backend.store import insert_sensor_data

    insert_sensor_data(msg1)
    insert_sensor_data(msg2)
    insert_sensor_data(msg3)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    dev = data[0]
    assert dev["device_id"] == "sensor_dht22_01"
    measurements = {m["type"]: m for m in dev["measurements"]}
    assert measurements["temperature"]["value"] == 25.5
    assert measurements["humidity"]["value"] == 62.1


@pytest.mark.asyncio
async def test_latest_empty_db():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/latest")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_latest_device_filter():
    from datetime import datetime, timezone

    msg1 = UnifiedMessage(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        timestamp=datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc),
        measurements=[
            Measurement(
                type=MeasurementType.TEMPERATURE, value=22.0, unit=Unit.CELSIUS
            ),
        ],
    )
    msg2 = UnifiedMessage(
        schema_version="v1",
        device_id="sensor_ir_01",
        subsystem=Subsystem.COUNTING,
        protocol=Protocol.MQTT,
        timestamp=datetime(2026, 7, 1, 10, 1, 0, tzinfo=timezone.utc),
        measurements=[
            Measurement(type=MeasurementType.COUNT, value=5.0, unit=Unit.COUNT),
        ],
    )

    from backend.store import insert_sensor_data

    insert_sensor_data(msg1)
    insert_sensor_data(msg2)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/latest?device_id=sensor_dht22_01")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["device_id"] == "sensor_dht22_01"
