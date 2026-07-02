# Integration tests for POST /api/v1/data — the sensor data ingestion endpoint.
# Uses httpx ASGI transport against the FastAPI app with a temporary SQLite DB.
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
    init_db()


@pytest.mark.asyncio
async def test_ingest_valid_single_measurement():
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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/data", json=msg.model_dump(mode="json"))
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data


@pytest.mark.asyncio
async def test_ingest_valid_multi_measurement():
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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/data", json=msg.model_dump(mode="json"))
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_ingest_missing_device_id():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/data",
            json={
                "schema_version": "v1",
                "device_id": "",
                "subsystem": "temp_humidity",
                "protocol": "mqtt",
                "measurements": [
                    {"type": "temperature", "value": 25.5, "unit": "celsius"}
                ],
            },
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_missing_measurements():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/data",
            json={
                "schema_version": "v1",
                "device_id": "sensor_dht22_01",
                "subsystem": "temp_humidity",
                "protocol": "mqtt",
                "measurements": [],
            },
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_missing_schema_version():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/data",
            json={
                "device_id": "sensor_dht22_01",
                "subsystem": "temp_humidity",
                "protocol": "mqtt",
                "measurements": [
                    {"type": "temperature", "value": 25.5, "unit": "celsius"}
                ],
            },
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_with_raw_payload():
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
        raw_payload={
            "topic": "factory/temp_humidity/sensors/sensor_dht22_01/temperature"
        },
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/data", json=msg.model_dump(mode="json"))
    assert resp.status_code == 201
