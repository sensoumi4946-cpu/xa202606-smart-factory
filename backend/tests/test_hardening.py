# Tests for command signing, fail-safe behaviour and the runtime state store.

import time
from datetime import datetime, timedelta, timezone

import pytest

from backend.security import command_signing as cs
from backend.services import failsafe


def command(action="close", device="valve_gas_main", issued=None):
    return {
        "command_id": "cmd-1",
        "device_id": device,
        "action": action,
        "params": {"mode": "emergency"},
        "issued_at": (issued or datetime.now(timezone.utc)).isoformat(),
    }


@pytest.fixture(autouse=True)
def _clean():
    cs.reset_nonces()
    failsafe.monitor.reset()
    yield
    cs.reset_nonces()


class TestSigning:
    def test_signed_command_verifies(self):
        signed = cs.attach_signature(command(), key="k")
        ok, reason = cs.verify(signed, key="k")
        assert ok and reason == "ok"

    def test_unsigned_command_is_rejected(self):
        ok, reason = cs.verify(command(), key="k")
        assert not ok and reason == "missing signature"

    def test_tampered_action_is_rejected(self):
        signed = cs.attach_signature(command("close"), key="k")
        signed["action"] = "open"
        ok, reason = cs.verify(signed, key="k")
        assert not ok and reason == "signature mismatch"

    def test_tampered_device_is_rejected(self):
        signed = cs.attach_signature(command(), key="k")
        signed["device_id"] = "someone_elses_valve"
        assert cs.verify(signed, key="k")[0] is False

    def test_tampered_params_are_rejected(self):
        signed = cs.attach_signature(command(), key="k")
        signed["params"] = {"mode": "normal"}
        assert cs.verify(signed, key="k")[0] is False

    def test_wrong_key_is_rejected(self):
        signed = cs.attach_signature(command(), key="k")
        assert cs.verify(signed, key="different")[0] is False

    def test_replayed_nonce_is_rejected(self):
        signed = cs.attach_signature(command(), key="k")
        assert cs.verify(dict(signed), key="k")[0] is True
        ok, reason = cs.verify(dict(signed), key="k")
        assert not ok and reason == "nonce replay"

    def test_stale_command_is_rejected(self):
        old = datetime.now(timezone.utc) - timedelta(minutes=5)
        signed = cs.attach_signature(command(issued=old), key="k")
        ok, reason = cs.verify(signed, key="k")
        assert not ok and "stale" in reason

    def test_each_command_gets_a_fresh_nonce(self):
        a = cs.attach_signature(command(), key="k")
        b = cs.attach_signature(command(), key="k")
        assert a["nonce"] != b["nonce"]

    def test_signature_is_deterministic_for_same_content(self):
        base = command()
        base["nonce"] = "fixed"
        assert cs.sign(base, "k") == cs.sign(dict(base), "k")

    def test_signing_disabled_without_key(self):
        with pytest.raises(cs.SigningDisabled):
            cs.sign(command(), key="")


class TestFailSafe:
    def test_gas_valve_closes_when_de_energised(self):
        spec = failsafe.spec_for("valve_gas_main")
        assert spec is not None
        assert spec.de_energised_action == "close"

    def test_exhaust_fan_keeps_running_when_de_energised(self):
        spec = failsafe.spec_for("hvac_exhaust_01")
        assert spec is not None
        assert spec.de_energised_action == "on"

    def test_agv_brakes_when_de_energised(self):
        spec = failsafe.spec_for("agv_01")
        assert spec is not None
        assert spec.de_energised_action == "stop"

    def test_every_spec_explains_itself(self):
        for spec in failsafe.FAIL_SAFE_SPECS.values():
            assert spec.rationale_zh

    def test_unknown_device_has_no_spec(self):
        assert failsafe.spec_for("nope") is None

    def test_link_starts_lost(self):
        assert failsafe.monitor.expired("valve_gas_main") is True

    def test_heartbeat_clears_expiry(self):
        failsafe.monitor.beat("valve_gas_main")
        assert failsafe.monitor.expired("valve_gas_main") is False

    def test_old_heartbeat_expires(self):
        failsafe.monitor.beat("valve_gas_main", at=time.time() - 300)
        assert failsafe.monitor.expired("valve_gas_main") is True

    def test_status_reports_safe_state_when_link_lost(self):
        rows = {r["device_id"]: r for r in failsafe.monitor.status()}
        assert rows["valve_gas_main"]["link"] == "lost"
        assert rows["valve_gas_main"]["current_safe_state"] == "close"

    def test_status_clears_safe_state_when_link_ok(self):
        for device in failsafe.FAIL_SAFE_SPECS:
            failsafe.monitor.beat(device)
        rows = {r["device_id"]: r for r in failsafe.monitor.status()}
        assert rows["valve_gas_main"]["current_safe_state"] is None

    def test_heartbeat_payload_carries_the_safe_action(self):
        payload = failsafe.heartbeat_payload("valve_gas_main")
        assert payload["de_energised_action"] == "close"
        assert payload["timeout_s"] > payload["interval_s"]


class TestRuntimeState:
    def test_single_worker_passes(self, monkeypatch):
        from backend import runtime_state

        monkeypatch.setattr(runtime_state, "WORKER_COUNT", 1)
        runtime_state.assert_single_worker()

    def test_multi_worker_is_refused_loudly(self, monkeypatch):
        from backend import runtime_state

        monkeypatch.setattr(runtime_state, "WORKER_COUNT", 4)
        with pytest.raises(runtime_state.MultiWorkerUnsupported) as exc:
            runtime_state.assert_single_worker()
        assert "runtime_state" in str(exc.value)

    def test_state_survives_cache_invalidation(self, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.config.DATABASE_PATH", str(tmp_path / "rs.db"))
        from backend.runtime_state import StateScope
        from backend.store import init_db

        init_db()
        scope = StateScope("test_scope")
        scope.set("k1", {"value": 42})
        scope.invalidate()
        assert scope.get("k1") == {"value": 42}

    def test_list_keeps_newest_first(self, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.config.DATABASE_PATH", str(tmp_path / "rs2.db"))
        from backend.runtime_state import StateList
        from backend.store import init_db

        init_db()
        items = StateList("test_list", max_items=10)
        for i in range(5):
            items.push({"n": i})
        assert items.recent(3)[0]["n"] == 4

    def test_list_is_bounded(self, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.config.DATABASE_PATH", str(tmp_path / "rs3.db"))
        from backend.runtime_state import StateList
        from backend.store import init_db

        init_db()
        items = StateList("bounded", max_items=5)
        for i in range(20):
            items.push({"n": i})
        assert len(items.recent(100)) <= 5
