import pytest
from httpx import ASGITransport, AsyncClient
from smart_factory_contracts.messages import Measurement, MeasurementType, Protocol, Subsystem, UnifiedMessage, Unit

from backend.main import app
from backend.store import init_db


@pytest.fixture(autouse=True)
def _init_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("backend.store.DATABASE_PATH", str(db_path))
    monkeypatch.setattr("backend.config.DATABASE_PATH", str(db_path))
    init_db()


async def _ingest(client, device_id, temp=25.0):
    msg = UnifiedMessage(
        device_id=device_id,
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        measurements=[
            Measurement(type=MeasurementType.TEMPERATURE, value=temp, unit=Unit.CELSIUS),
        ],
    )
    await client.post("/api/v1/data", json=msg.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_query_empty():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/data")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_query_by_device():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _ingest(client, "sensor_dht22_01", 25.0)
        await _ingest(client, "sensor_dht22_01", 26.0)
        await _ingest(client, "sensor_dht22_01", 27.0)

        resp = await client.get("/api/v1/data", params={"device_id": "sensor_dht22_01", "limit": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3


@pytest.mark.asyncio
async def test_query_limit():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for i in range(5):
            await _ingest(client, "sensor_dht22_01", 25.0 + i)

        resp = await client.get("/api/v1/data", params={"limit": 2})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_query_all_devices():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _ingest(client, "sensor_dht22_01", 25.0)
        await _ingest(client, "sensor_mq2_01", 0.0)
        await _ingest(client, "sensor_pir_01", 1.0)

        resp = await client.get("/api/v1/devices")
    assert resp.status_code == 200
    devices = resp.json()
    assert len(devices) == 3
    assert "sensor_dht22_01" in devices
    assert "sensor_mq2_01" in devices
    assert "sensor_pir_01" in devices


@pytest.mark.asyncio
async def test_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
