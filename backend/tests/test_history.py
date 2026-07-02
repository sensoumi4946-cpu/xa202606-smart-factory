# Integration tests for GET /api/v1/history.
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
async def test_history_time_range():
    for i in range(5):
        msg = UnifiedMessage(
            schema_version="v1",
            device_id="sensor_dht22_01",
            subsystem=Subsystem.TEMP_HUMIDITY,
            protocol=Protocol.MQTT,
            timestamp=datetime(2026, 7, 1, 10, i, 0, tzinfo=timezone.utc),
            measurements=[
                Measurement(
                    type=MeasurementType.TEMPERATURE,
                    value=float(20 + i),
                    unit=Unit.CELSIUS,
                ),
            ],
        )
        insert_sensor_data(msg)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        url = "/api/v1/history?since=2026-07-01T10:01:00Z&until=2026-07-01T10:03:00Z"
        resp = await client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2  # 10:01, 10:02, 10:03


@pytest.mark.asyncio
async def test_history_pagination():
    for i in range(10):
        msg = UnifiedMessage(
            schema_version="v1",
            device_id="sensor_dht22_01",
            subsystem=Subsystem.TEMP_HUMIDITY,
            protocol=Protocol.MQTT,
            timestamp=datetime(2026, 7, 1, 10, i, 0, tzinfo=timezone.utc),
            measurements=[
                Measurement(
                    type=MeasurementType.TEMPERATURE,
                    value=float(20 + i),
                    unit=Unit.CELSIUS,
                ),
            ],
        )
        insert_sensor_data(msg)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/history?limit=3&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 3
    assert data["total"] == 10


@pytest.mark.asyncio
async def test_history_until_before_since_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/history?since=2026-07-02T00:00:00Z&until=2026-07-01T00:00:00Z"
        )
    assert resp.status_code == 422
