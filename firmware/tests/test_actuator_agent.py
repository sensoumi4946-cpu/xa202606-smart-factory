import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sim.actuator_agent import ActuatorAgent  


@pytest.fixture
def agent(monkeypatch):
    a = ActuatorAgent(
        device_id="relay_lighting_01",
        subsystem="lighting",
        broker_host="localhost",
        broker_port=1883,
    )
    a.client = SimpleNamespace(subscribe=lambda *args, **kwargs: None)
    return a


@pytest.fixture
def acks(monkeypatch):
    sent = []

    def _capture(url, json=None, headers=None, timeout=None):
        sent.append({"url": url, "body": json})
        return SimpleNamespace(status_code=200, text="")

    import sim.actuator_agent

    monkeypatch.setattr(sim.actuator_agent.requests, "post", _capture)
    return sent


def _message(agent, action, params=None, command_id="cmd-1", ack_url="http://x/ack"):
    payload = {
        "command_id": command_id,
        "device_id": agent.device_id,
        "action": action,
        "params": params or {},
        "ack_url": ack_url,
    }
    return SimpleNamespace(
        topic=agent.topic,
        payload=json.dumps(payload).encode("utf-8"),
    )


class TestActuation:
    def test_starts_off(self, agent):
        assert agent.relay_state == "off"

    def test_on_switches_relay(self, agent):
        ok, detail = agent._actuate("on", {})
        assert ok
        assert agent.relay_state == "on"
        assert "relay=on" in detail

    def test_off_switches_relay(self, agent):
        agent._actuate("on", {})
        ok, _ = agent._actuate("off", {})
        assert ok
        assert agent.relay_state == "off"

    def test_toggle_flips_state(self, agent):
        agent._actuate("toggle", {})
        assert agent.relay_state == "on"
        agent._actuate("toggle", {})
        assert agent.relay_state == "off"

    def test_dim_accepts_valid_brightness(self, agent):
        ok, _ = agent._actuate("dim", {"brightness": 40})
        assert ok
        assert agent.relay_state == "dim:40"

    def test_dim_rejects_out_of_range(self, agent):
        ok, detail = agent._actuate("dim", {"brightness": 500})
        assert not ok
        assert "between 0 and 100" in detail

    def test_dim_rejects_non_numeric(self, agent):
        ok, _ = agent._actuate("dim", {"brightness": "bright"})
        assert not ok

    def test_unsupported_action_is_rejected_not_ignored(self, agent):
        ok, detail = agent._actuate("explode", {})
        assert not ok
        assert "unsupported" in detail

    def test_reset_returns_to_off(self, agent):
        agent._actuate("on", {})
        agent._actuate("reset", {})
        assert agent.relay_state == "off"


class TestMessageHandling:
    def test_valid_command_acts_and_acks(self, agent, acks):
        agent._on_message(None, None, _message(agent, "on"))
        assert agent.relay_state == "on"
        assert len(acks) == 1
        assert acks[0]["body"]["success"] is True

    def test_failed_command_acks_with_reason(self, agent, acks):
        agent._on_message(None, None, _message(agent, "dim", {"brightness": 999}))
        assert len(acks) == 1
        assert acks[0]["body"]["success"] is False
        assert "between 0 and 100" in acks[0]["body"]["detail"]

    def test_malformed_json_is_dropped(self, agent, acks):
        msg = SimpleNamespace(topic=agent.topic, payload=b"not json at all")
        agent._on_message(None, None, msg)
        assert agent.relay_state == "off"
        assert acks == []

    def test_command_without_id_is_ignored(self, agent, acks):
        payload = {"action": "on", "ack_url": "http://x/ack"}
        msg = SimpleNamespace(
            topic=agent.topic, payload=json.dumps(payload).encode("utf-8")
        )
        agent._on_message(None, None, msg)
        assert agent.relay_state == "off"
        assert acks == []

    def test_command_without_action_is_ignored(self, agent, acks):
        payload = {"command_id": "c1", "ack_url": "http://x/ack"}
        msg = SimpleNamespace(
            topic=agent.topic, payload=json.dumps(payload).encode("utf-8")
        )
        agent._on_message(None, None, msg)
        assert acks == []

    def test_missing_ack_url_still_actuates(self, agent, acks):
        payload = {"command_id": "c1", "action": "on"}
        msg = SimpleNamespace(
            topic=agent.topic, payload=json.dumps(payload).encode("utf-8")
        )
        agent._on_message(None, None, msg)
        assert agent.relay_state == "on"
        assert acks == []

    def test_backend_down_does_not_crash_agent(self, agent, monkeypatch):
        import sim.actuator_agent as actuator_agent

        def _boom(*args, **kwargs):
            raise actuator_agent.requests.RequestException("connection refused")

        monkeypatch.setattr(actuator_agent.requests, "post", _boom)
        agent._on_message(None, None, _message(agent, "on"))
        
        assert agent.relay_state == "on"

    def test_api_key_is_sent_when_configured(self, agent, monkeypatch):
        captured = {}

        def _capture(url, json=None, headers=None, timeout=None):
            captured["headers"] = headers
            return SimpleNamespace(status_code=200, text="")

        import sim.actuator_agent as actuator_agent

        monkeypatch.setattr(actuator_agent.requests, "post", _capture)
        agent.api_key = "secret-key"
        agent._on_message(None, None, _message(agent, "on"))
        assert captured["headers"]["X-API-Key"] == "secret-key"


class TestTopic:
    def test_topic_matches_backend_convention(self, agent):
        assert agent.topic == "factory/lighting/control/relay_lighting_01"

    def test_topic_uses_given_subsystem(self):
        a = ActuatorAgent("agv_01", "agv", "localhost", 1883)
        assert a.topic == "factory/agv/control/agv_01"
