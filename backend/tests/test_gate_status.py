import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.store import init_db


@pytest.fixture(autouse=True)
def _init_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("backend.store.DATABASE_PATH", str(db_path))
    monkeypatch.setattr("backend.config.DATABASE_PATH", str(db_path))
    init_db()


@pytest.mark.asyncio
async def test_gate_status_waits_before_any_ingest():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/semantic/gate-status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "waiting"
    assert resp.json()["reason"] == "no ingest activity yet"


@pytest.mark.asyncio
async def test_gate_status_reflects_passed_ingest():
    payload = {
        "schema_version": "v1",
        "device_id": "sensor_dht22_01",
        "subsystem": "temp_humidity",
        "protocol": "mqtt",
        "measurements": [{"type": "temperature", "value": 25.0, "unit": "celsius"}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/ingest/api/v1/data", json=payload)
        resp = await client.get("/api/v1/semantic/gate-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "passed"
    assert body["last_device"] == "sensor_dht22_01"
    assert body["passed_count"] == 1


@pytest.mark.asyncio
async def test_gate_status_reflects_rejected_ingest():
    payload = {
        "schema_version": "v1",
        "device_id": "sensor_dht22_01",
        "subsystem": "temp_humidity",
        "protocol": "mqtt",
        "measurements": [{"type": "temperature", "value": 9999.0, "unit": "celsius"}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/ingest/api/v1/data", json=payload)
        resp = await client.get("/api/v1/semantic/gate-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["rejected_count"] == 1


@pytest.mark.asyncio
async def test_semantic_query_requires_query_field():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/semantic/query", json={})
    assert resp.status_code == 422
