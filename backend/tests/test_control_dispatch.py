# Tests for the end-to-end control loop. Tests check that a command is published, 
# that the status machine moves pending -> dispatched -> executed, and that
# a dead broker degrades to 'failed' instead of a 500.

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.services import control_dispatcher
from backend.store import get_control_status, init_db


@pytest.fixture(autouse=True)
def _init_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("backend.store.DATABASE_PATH", str(db_path))
    monkeypatch.setattr("backend.config.DATABASE_PATH", str(db_path))
    init_db()


@pytest.fixture
def published(monkeypatch):
    """Capture what would have gone to the broker"""
    sent = []

    def _fake_publish(topic, payload):
        sent.append((topic, payload))

    monkeypatch.setattr(control_dispatcher, "_publish_blocking", _fake_publish)
    return sent


@pytest.fixture
def broker_down(monkeypatch):
    def _fake_publish(topic, payload):
        raise ConnectionRefusedError("no broker here")

    monkeypatch.setattr(control_dispatcher, "_publish_blocking", _fake_publish)


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_command_is_published_to_mqtt(published):
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/control",
            json={
                "device_id": "relay_lighting_01",
                "action": "on",
                "subsystem": "lighting",
            },
        )

    assert resp.status_code == 202
    body = resp.json()
    assert body["dispatched"] is True
    assert body["status"] == "dispatched"

    assert len(published) == 1
    topic, payload = published[0]
    assert topic == "factory/lighting/control/relay_lighting_01"
    assert payload["action"] == "on"
    assert payload["command_id"] == body["command_id"]
    assert payload["ack_url"].endswith(f"/api/v1/control/{body['command_id']}/ack")


@pytest.mark.asyncio
async def test_status_moves_to_dispatched(published):
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/control", json={"device_id": "relay_02", "action": "off"}
        )
        command_id = resp.json()["command_id"]
        status_resp = await client.get(f"/api/v1/control/{command_id}")

    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["status"] == "dispatched"
    assert data["dispatched_at"] is not None
    assert data["acked_at"] is None


@pytest.mark.asyncio
async def test_device_ack_marks_executed(published):
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/control", json={"device_id": "relay_03", "action": "toggle"}
        )
        command_id = resp.json()["command_id"]

        ack = await client.post(
            f"/api/v1/control/{command_id}/ack",
            json={"success": True, "detail": "relay=on"},
        )

    assert ack.status_code == 200
    data = ack.json()
    assert data["status"] == "executed"
    assert data["acked_at"] is not None
    assert data["result"] == "relay=on"


@pytest.mark.asyncio
async def test_device_can_report_failure(published):
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/control", json={"device_id": "relay_04", "action": "dim"}
        )
        command_id = resp.json()["command_id"]

        ack = await client.post(
            f"/api/v1/control/{command_id}/ack",
            json={"success": False, "detail": "brightness out of range"},
        )

    assert ack.json()["status"] == "failed"
    assert ack.json()["result"] == "brightness out of range"


@pytest.mark.asyncio
async def test_ack_is_idempotent(published):
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/control", json={"device_id": "relay_05", "action": "on"}
        )
        command_id = resp.json()["command_id"]

        first = await client.post(
            f"/api/v1/control/{command_id}/ack",
            json={"success": True, "detail": "relay=on"},
        )
        second = await client.post(
            f"/api/v1/control/{command_id}/ack",
            json={"success": False, "detail": "should be ignored"},
        )

    assert first.json()["status"] == "executed"
    assert second.json()["status"] == "executed"
    assert second.json()["result"] == "relay=on"


@pytest.mark.asyncio
async def test_ack_unknown_command_is_404(published):
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/control/does-not-exist/ack", json={"success": True}
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_broker_down_does_not_500(broker_down):
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/control", json={"device_id": "relay_06", "action": "on"}
        )

    assert resp.status_code == 202
    body = resp.json()
    assert body["dispatched"] is False
    assert body["status"] == "failed"

    cmd = get_control_status(body["command_id"])
    assert cmd is not None, f"Command {body['command_id']} was not found or returned None"
    assert cmd["status"] == "failed"
    assert cmd["result"] == "broker unreachable"


@pytest.mark.asyncio
async def test_control_log_lists_recent_commands(published):
    async with await _client() as client:
        for action in ("on", "off", "on"):
            await client.post(
                "/api/v1/control",
                json={"device_id": "relay_07", "action": action},
            )
        log_resp = await client.get("/api/v1/control?device_id=relay_07")

    assert log_resp.status_code == 200
    items = log_resp.json()["items"]
    assert len(items) == 3
    assert all(i["device_id"] == "relay_07" for i in items)


@pytest.mark.asyncio
async def test_control_log_filters_by_device(published):
    async with await _client() as client:
        await client.post("/api/v1/control", json={"device_id": "relay_A", "action": "on"})
        await client.post("/api/v1/control", json={"device_id": "relay_B", "action": "on"})
        resp = await client.get("/api/v1/control?device_id=relay_A")

    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["device_id"] == "relay_A"
