# Integration tests for GET /api/v1/devices — real device registry
# (protocol, subsystem, last_seen) built from actually ingested data.
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
from backend.store import init_db, insert_sensor_data


@pytest.fixture(autouse=True)
def _init_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("backend.store.DATABASE_PATH", str(db_path))
    monkeypatch.setattr("backend.config.DATABASE_PATH", str(db_path))
    init_db()


@pytest.mark.asyncio
async def test_old_devices_endpoint_still_returns_plain_id_list():
    insert_sensor_data(UnifiedMessage(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        measurements=[Measurement(type=MeasurementType.TEMPERATURE, value=25.0, unit=Unit.CELSIUS)],
    ))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/devices")
    assert resp.status_code == 200
    body = resp.json()
    assert body == ["sensor_dht22_01"]
    assert isinstance(body[0], str)


@pytest.mark.asyncio
async def test_empty_registry_when_no_data():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/devices/registry")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_registry_reports_protocol_and_subsystem_per_device():
    insert_sensor_data(UnifiedMessage(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        measurements=[Measurement(type=MeasurementType.TEMPERATURE, value=25.0, unit=Unit.CELSIUS)],
    ))
    insert_sensor_data(UnifiedMessage(
        schema_version="v1",
        device_id="sensor_mq2_01",
        subsystem=Subsystem.GAS,
        protocol=Protocol.MODBUS,
        measurements=[Measurement(type=MeasurementType.CO, value=5.0, unit=Unit.PPM)],
    ))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/devices/registry")
    assert resp.status_code == 200
    body = resp.json()
    by_id = {d["device_id"]: d for d in body}

    assert by_id["sensor_dht22_01"]["protocol"] == "mqtt"
    assert by_id["sensor_dht22_01"]["subsystem"] == "temp_humidity"
    assert "last_seen" in by_id["sensor_dht22_01"]

    assert by_id["sensor_mq2_01"]["protocol"] == "modbus"
    assert by_id["sensor_mq2_01"]["subsystem"] == "gas"


@pytest.mark.asyncio
async def test_registry_has_one_entry_per_device_not_per_reading():
    for value in [20.0, 21.0, 22.0]:
        insert_sensor_data(UnifiedMessage(
            schema_version="v1",
            device_id="sensor_dht22_01",
            subsystem=Subsystem.TEMP_HUMIDITY,
            protocol=Protocol.MQTT,
            measurements=[Measurement(type=MeasurementType.TEMPERATURE, value=value, unit=Unit.CELSIUS)],
        ))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/devices/registry")
    body = resp.json()
    assert len(body) == 1
    assert body[0]["device_id"] == "sensor_dht22_01"


@pytest.mark.asyncio
async def test_registry_reflects_most_recent_reading_last_seen():
    insert_sensor_data(UnifiedMessage(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        measurements=[Measurement(type=MeasurementType.TEMPERATURE, value=20.0, unit=Unit.CELSIUS)],
    ))
    insert_sensor_data(UnifiedMessage(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        measurements=[Measurement(type=MeasurementType.TEMPERATURE, value=21.0, unit=Unit.CELSIUS)],
    ))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/devices/registry")
    body = resp.json()
    first_seen = body[0]["last_seen"]
    assert first_seen is not None
