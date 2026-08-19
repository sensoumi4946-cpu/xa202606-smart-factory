import sqlite3

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.security import command_audit, device_keys
from backend.store import init_db


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    path = tmp_path / "sec.db"
    monkeypatch.setattr("backend.store.DATABASE_PATH", str(path))
    monkeypatch.setattr("backend.config.DATABASE_PATH", str(path))
    init_db()
    return path


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestDeviceKeys:
    def test_enrolled_key_resolves_to_its_device(self):
        issued = device_keys.enroll_device("esp32_01_dht22", ["ingest"])
        identity = device_keys.resolve_key(issued["api_key"])
        assert identity is not None
        assert identity["device_id"] == "esp32_01_dht22"
        assert identity["scopes"] == ["ingest"]

    def test_plaintext_key_is_never_stored(self, _db):
        issued = device_keys.enroll_device("esp32_01_dht22")
        conn = sqlite3.connect(str(_db))
        rows = conn.execute("SELECT * FROM device_keys").fetchall()
        conn.close()
        blob = str(rows)
        assert issued["api_key"] not in blob

    def test_each_device_gets_a_distinct_key(self):
        a = device_keys.enroll_device("dev_a")
        b = device_keys.enroll_device("dev_b")
        assert a["api_key"] != b["api_key"]
        identity = device_keys.resolve_key(a["api_key"])
        assert identity is not None
        assert identity["device_id"] == "dev_a"

    def test_unknown_key_resolves_to_nothing(self):
        assert device_keys.resolve_key("xa_fake_nonsense") is None

    def test_empty_key_is_rejected(self):
        assert device_keys.resolve_key("") is None

    def test_revoked_key_stops_working_immediately(self):
        issued = device_keys.enroll_device("dev_c")
        device_keys.revoke_key(issued["key_id"])
        assert device_keys.resolve_key(issued["api_key"]) is None

    def test_revoking_one_device_leaves_others_alone(self):
        a = device_keys.enroll_device("dev_a")
        b = device_keys.enroll_device("dev_b")
        device_keys.revoke_device("dev_a")
        assert device_keys.resolve_key(a["api_key"]) is None
        assert device_keys.resolve_key(b["api_key"]) is not None

    def test_rotation_invalidates_the_old_key(self):
        first = device_keys.enroll_device("dev_d", ["ingest", "control"])
        second = device_keys.rotate_key(first["key_id"])
        assert second is not None
        assert device_keys.resolve_key(first["api_key"]) is None
        identity = device_keys.resolve_key(second["api_key"])
        assert identity is not None
        assert identity["device_id"] == "dev_d"
        assert set(identity["scopes"]) == {"ingest", "control"}

    def test_sensor_key_cannot_actuate(self):
        issued = device_keys.enroll_device("esp32_01_dht22", ["ingest"])
        identity = device_keys.resolve_key(issued["api_key"])
        assert identity is not None
        assert device_keys.has_scope(identity, "ingest")
        assert not device_keys.has_scope(identity, "control")

    def test_admin_scope_implies_everything(self):
        issued = device_keys.enroll_device("console", ["admin"])
        identity = device_keys.resolve_key(issued["api_key"])
        assert identity is not None
        assert device_keys.has_scope(identity, "control")
        assert device_keys.has_scope(identity, "ingest")

    def test_no_identity_has_no_scope(self):
        assert not device_keys.has_scope(None, "ingest")

    def test_invalid_scope_is_rejected_at_enrolment(self):
        with pytest.raises(ValueError):
            device_keys.enroll_device("dev_e", ["superuser"])

    def test_usage_is_counted(self):
        issued = device_keys.enroll_device("dev_f")
        device_keys.resolve_key(issued["api_key"])
        device_keys.resolve_key(issued["api_key"])
        record = device_keys.list_keys("dev_f")[0]
        assert record["use_count"] == 2
        assert record["last_used_at"] is not None


class TestAuditChain:
    def test_empty_log_is_valid(self):
        assert command_audit.verify_chain()["valid"] is True

    def test_entries_chain_together(self):
        first = command_audit.record("valve_gas_main", "close", "dispatched")
        second = command_audit.record("valve_gas_main", "open", "dispatched")
        assert first["prev_hash"] == command_audit.GENESIS_HASH
        assert second["prev_hash"] == first["entry_hash"]
        assert command_audit.verify_chain()["valid"] is True

    def test_editing_a_row_breaks_the_chain(self, _db):
        command_audit.record("valve_gas_main", "close", "dispatched")
        command_audit.record("hvac_exhaust_01", "on", "dispatched")

        conn = sqlite3.connect(str(_db))
        conn.execute("UPDATE command_audit SET action = 'open' WHERE seq = 1")
        conn.commit()
        conn.close()

        report = command_audit.verify_chain()
        assert report["valid"] is False
        assert report["broken_at_seq"] == 1
        assert "modified" in report["reason"]

    def test_deleting_a_row_breaks_the_chain(self, _db):
        command_audit.record("d1", "on", "dispatched")
        command_audit.record("d2", "on", "dispatched")
        command_audit.record("d3", "on", "dispatched")

        conn = sqlite3.connect(str(_db))
        conn.execute("DELETE FROM command_audit WHERE seq = 2")
        conn.commit()
        conn.close()

        report = command_audit.verify_chain()
        assert report["valid"] is False
        assert "deleted" in report["reason"] or "reordered" in report["reason"]

    def test_actor_is_recorded(self):
        command_audit.record(
            "valve_gas_main",
            "close",
            "dispatched",
            actor="safety_controller:gas_isolation",
        )
        entry = command_audit.query(device_id="valve_gas_main")[0]
        assert entry["actor"] == "safety_controller:gas_isolation"

    def test_query_filters_by_outcome(self):
        command_audit.record("d1", "on", "executed")
        command_audit.record("d2", "on", "failed")
        assert len(command_audit.query(outcome="failed")) == 1

    def test_query_filters_by_command_id(self):
        command_audit.record("d1", "on", "executed", command_id="cmd-1")
        command_audit.record("d1", "off", "executed", command_id="cmd-2")
        assert len(command_audit.query(command_id="cmd-1")) == 1

    def test_denied_attempts_are_logged(self):
        command_audit.record(
            "valve_gas_main", "close", command_audit.OUTCOME_DENIED,
            actor="unknown", detail="key lacks control scope",
        )
        entry = command_audit.query(outcome="denied")[0]
        assert entry["detail"] == "key lacks control scope"


class TestSecurityApi:
    @pytest.mark.asyncio
    async def test_enroll_returns_key_once(self):
        async with await _client() as c:
            resp = await c.post(
                "/api/v1/security/devices/enroll",
                json={"device_id": "esp32_01_dht22", "scopes": ["ingest"]},
            )
        assert resp.status_code == 201
        assert resp.json()["api_key"].startswith("xa_esp32_01_dht22_")

    @pytest.mark.asyncio
    async def test_listed_keys_never_include_plaintext(self):
        async with await _client() as c:
            created = await c.post(
                "/api/v1/security/devices/enroll", json={"device_id": "d1"}
            )
            listed = await c.get("/api/v1/security/devices/keys")
        assert created.json()["api_key"] not in listed.text

    @pytest.mark.asyncio
    async def test_whoami_identifies_the_caller(self):
        async with await _client() as c:
            created = await c.post(
                "/api/v1/security/devices/enroll",
                json={"device_id": "d2", "scopes": ["control"]},
            )
            key = created.json()["api_key"]
            me = await c.get("/api/v1/security/whoami", headers={"X-API-Key": key})
        assert me.status_code == 200
        assert me.json()["device_id"] == "d2"

    @pytest.mark.asyncio
    async def test_whoami_rejects_a_revoked_key(self):
        async with await _client() as c:
            created = await c.post(
                "/api/v1/security/devices/enroll", json={"device_id": "d3"}
            )
            body = created.json()
            await c.post(f"/api/v1/security/devices/keys/{body['key_id']}/revoke")
            me = await c.get(
                "/api/v1/security/whoami", headers={"X-API-Key": body["api_key"]}
            )
        assert me.status_code == 401

    @pytest.mark.asyncio
    async def test_revoking_twice_is_404(self):
        async with await _client() as c:
            created = await c.post(
                "/api/v1/security/devices/enroll", json={"device_id": "d4"}
            )
            kid = created.json()["key_id"]
            await c.post(f"/api/v1/security/devices/keys/{kid}/revoke")
            second = await c.post(f"/api/v1/security/devices/keys/{kid}/revoke")
        assert second.status_code == 404

    @pytest.mark.asyncio
    async def test_audit_verify_endpoint_reports_valid(self):
        command_audit.record("d1", "on", "executed")
        async with await _client() as c:
            resp = await c.get("/api/v1/security/audit/verify")
        assert resp.json()["valid"] is True