# Edge-case tests for POST /api/v1/data
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
async def test_missing_device_id_returns_422():
    payload = {
        "schema_version": "v1",
        "subsystem": "temp_humidity",
        "protocol": "mqtt",
        "measurements": [{"type": "temperature", "value": 25.0, "unit": "celsius"}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/ingest/api/v1/data", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_empty_measurements_list_returns_422():
    payload = {
        "schema_version": "v1",
        "device_id": "sensor_dht22_01",
        "subsystem": "temp_humidity",
        "protocol": "mqtt",
        "measurements": [],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/ingest/api/v1/data", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unknown_subsystem_enum_rejected_before_shacl():
    payload = {
        "schema_version": "v1",
        "device_id": "sensor_x",
        "subsystem": "not_a_real_subsystem",
        "protocol": "mqtt",
        "measurements": [{"type": "temperature", "value": 25.0, "unit": "celsius"}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/ingest/api/v1/data", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_temperature_far_out_of_physical_range_rejected_by_shacl():
    payload = {
        "schema_version": "v1",
        "device_id": "sensor_dht22_01",
        "subsystem": "temp_humidity",
        "protocol": "mqtt",
        "measurements": [{"type": "temperature", "value": 9999.0, "unit": "celsius"}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/ingest/api/v1/data", json=payload)
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body


@pytest.mark.asyncio
async def test_wrong_unit_for_measurement_type_rejected_by_shacl():
    payload = {
        "schema_version": "v1",
        "device_id": "sensor_mq2_01",
        "subsystem": "gas",
        "protocol": "modbus",
        "measurements": [{"type": "co", "value": 5.0, "unit": "celsius"}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/ingest/api/v1/data", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_boundary_value_at_exact_limit_is_accepted():
    payload = {
        "schema_version": "v1",
        "device_id": "sensor_dht22_01",
        "subsystem": "temp_humidity",
        "protocol": "mqtt",
        "measurements": [{"type": "humidity", "value": 100.0, "unit": "percent"}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/ingest/api/v1/data", json=payload)
    assert resp.status_code == 200
