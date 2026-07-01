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
async def test_control_create():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/control", json={
            "device_id": "relay_01",
            "action": "on",
            "params": {},
        })
    assert resp.status_code == 202
    data = resp.json()
    assert "command_id" in data


@pytest.mark.asyncio
async def test_control_with_params():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/control", json={
            "device_id": "relay_02",
            "action": "dim",
            "params": {"brightness": 50},
        })
    assert resp.status_code == 202
    data = resp.json()
    assert "command_id" in data


@pytest.mark.asyncio
async def test_control_status():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/v1/control", json={
            "device_id": "relay_03",
            "action": "off",
        })
        command_id = create_resp.json()["command_id"]

        status_resp = await client.get(f"/api/v1/control/{command_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["command_id"] == command_id
    assert status_data["status"] == "pending"
    assert status_data["device_id"] == "relay_03"


@pytest.mark.asyncio
async def test_control_status_not_found():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/control/nonexistent")
    assert resp.status_code == 404
