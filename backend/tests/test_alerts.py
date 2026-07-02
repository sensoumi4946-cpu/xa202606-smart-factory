# Integration tests for GET /api/v1/alerts.
import pytest
from datetime import datetime, timezone

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
async def test_alerts_query():
    msg = UnifiedMessage(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        measurements=[
            Measurement(type=MeasurementType.TEMPERATURE, value=39.0, unit=Unit.CELSIUS),
        ],
    )
    insert_sensor_data(msg)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/alerts?limit=20")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["rule_name"] == "high_temp"


@pytest.mark.asyncio
async def test_alerts_filter_by_level():
    msg = UnifiedMessage(
        schema_version="v1",
        device_id="sensor_mq2_01",
        subsystem=Subsystem.GAS,
        protocol=Protocol.MQTT,
        measurements=[
            Measurement(type=MeasurementType.CO, value=40.0, unit=Unit.PPM),
        ],
    )
    insert_sensor_data(msg)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/alerts?level=warning")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0  # CO is critical

    async with AsyncClient(transport=transport, base_url="http://test") as client2:
        resp2 = await client2.get("/api/v1/alerts?level=critical")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["total"] == 1


@pytest.mark.asyncio
async def test_alerts_empty():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_alerts_invalid_level_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/alerts?level=info")
    assert resp.status_code == 422
