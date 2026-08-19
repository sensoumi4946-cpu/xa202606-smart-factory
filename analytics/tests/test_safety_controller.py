import pytest

from analytics.safety_controller import (
    Policy,
    SafetyController,
    execute_actions,
)


@pytest.fixture
def ctl():
    return SafetyController(min_interval_s=20.0, clear_hold_s=30.0)


def hazard(rule_name: str) -> dict:
    return {"rule_name": rule_name, "severity": "critical"}


class TestGasIsolation:
    def test_gas_leak_closes_the_valve(self, ctl):
        actions = ctl.on_hazards([hazard("gas_leak_unattended")], timestamp=100.0)
        assert len(actions) == 1
        assert actions[0].device_id == "valve_gas_main"
        assert actions[0].action == "close"
        assert actions[0].params["mode"] == "emergency"

    def test_smouldering_also_closes_the_valve(self, ctl):
        actions = ctl.on_hazards([hazard("smouldering")], timestamp=100.0)
        assert any(a.policy_name == "gas_isolation" for a in actions)

    def test_valve_stays_closed_while_hazard_persists(self, ctl):
        ctl.on_hazards([hazard("gas_leak_unattended")], timestamp=100.0)
        again = ctl.on_hazards([hazard("gas_leak_unattended")], timestamp=105.0)
        assert again == []
        assert ctl.is_engaged("gas_isolation")

    def test_valve_reopens_after_hazard_clears(self, ctl):
        ctl.on_hazards([hazard("gas_leak_unattended")], timestamp=100.0)
        released = ctl.tick(timestamp=200.0)
        assert len(released) == 1
        assert released[0].action == "open"
        assert not ctl.is_engaged("gas_isolation")

    def test_no_release_before_hold_expires(self, ctl):
        ctl.on_hazards([hazard("gas_leak_unattended")], timestamp=100.0)
        assert ctl.tick(timestamp=110.0) == []
        assert ctl.is_engaged("gas_isolation")

    def test_hold_extends_while_hazard_keeps_firing(self, ctl):
        ctl.on_hazards([hazard("gas_leak_unattended")], timestamp=100.0)
        ctl.on_hazards([hazard("gas_leak_unattended")], timestamp=125.0)
        # Refreshed at 125, so at 140 only 15s have elapsed since refresh
        assert ctl.tick(timestamp=140.0) == []
        assert ctl.tick(timestamp=160.0)


class TestHvac:
    def test_fire_risk_starts_exhaust_at_full_speed(self, ctl):
        actions = ctl.on_hazards([hazard("fire_risk")], timestamp=100.0)
        hvac = [a for a in actions if a.policy_name == "fire_ventilation"]
        assert len(hvac) == 1
        assert hvac[0].device_id == "hvac_exhaust_01"
        assert hvac[0].params["speed"] == 100
        assert hvac[0].params["mode"] == "exhaust"

    def test_condensation_runs_dehumidify_not_exhaust(self, ctl):
        actions = ctl.on_hazards([hazard("condensation_risk")], timestamp=100.0)
        assert actions[0].params["mode"] == "dehumidify"
        assert actions[0].params["speed"] == 60
        assert actions[0].severity == "warning"

    def test_hvac_switches_off_when_clear(self, ctl):
        ctl.on_hazards([hazard("fire_risk")], timestamp=100.0)
        released = ctl.tick(timestamp=200.0)
        assert released[0].action == "off"


class TestSafetyInterlocks:
    def test_manual_override_blocks_automation(self, ctl):
        ctl.set_manual_override("gas_isolation", True)
        actions = ctl.on_hazards([hazard("gas_leak_unattended")], timestamp=100.0)
        assert actions == []

    def test_override_can_be_lifted(self, ctl):
        ctl.set_manual_override("gas_isolation", True)
        ctl.on_hazards([hazard("gas_leak_unattended")], timestamp=100.0)
        ctl.set_manual_override("gas_isolation", False)
        actions = ctl.on_hazards([hazard("gas_leak_unattended")], timestamp=130.0)
        assert len(actions) == 1

    def test_override_prevents_automatic_release(self, ctl):
        ctl.on_hazards([hazard("gas_leak_unattended")], timestamp=100.0)
        ctl.set_manual_override("gas_isolation", True)
        assert ctl.tick(timestamp=300.0) == []

    def test_disabled_controller_does_nothing(self):
        ctl = SafetyController(enabled=False)
        assert ctl.on_hazards([hazard("fire_risk")], timestamp=100.0) == []
        assert ctl.tick(timestamp=200.0) == []

    def test_rate_limit_blocks_rapid_recycling(self, ctl):
        ctl.on_hazards([hazard("gas_leak_unattended")], timestamp=100.0)
        ctl.tick(timestamp=200.0)
        # Released at 200; re-engaging at 205 would cycle the valve twice in
        # five seconds, which damages real actuators
        assert ctl.on_hazards([hazard("gas_leak_unattended")], timestamp=205.0) == []
        assert ctl.on_hazards([hazard("gas_leak_unattended")], timestamp=230.0)

    def test_unrelated_hazard_triggers_nothing(self, ctl):
        assert ctl.on_hazards([hazard("agv_collision_risk")], timestamp=100.0) == []

    def test_one_hazard_can_drive_two_policies(self):
        ctl = SafetyController(
            policies=[
                Policy("a", "A", ("fire_risk",), "dev_a", "s", "on", "off"),
                Policy("b", "B", ("fire_risk",), "dev_b", "s", "on", "off"),
            ]
        )
        actions = ctl.on_hazards([hazard("fire_risk")], timestamp=100.0)
        assert {a.device_id for a in actions} == {"dev_a", "dev_b"}

    def test_history_records_engage_and_release(self, ctl):
        ctl.on_hazards([hazard("fire_risk")], timestamp=100.0)
        ctl.tick(timestamp=200.0)
        history = ctl.history()
        assert len(history) == 2
        assert history[0]["action"] == "off"
        assert history[1]["action"] == "on"


class TestExecution:
    @pytest.mark.asyncio
    async def test_actions_are_dispatched_and_audited(self, ctl):
        sent, audited = [], []

        async def fake_dispatch(command_id, device_id, action, params, subsystem):
            sent.append((device_id, action, subsystem))
            return True

        def fake_audit(**kwargs):
            audited.append(kwargs)

        actions = ctl.on_hazards([hazard("fire_risk")], timestamp=100.0)
        results = await execute_actions(
            actions, dispatch=fake_dispatch, audit=fake_audit
        )

        assert sent == [("hvac_exhaust_01", "on", "hvac")]
        assert results[0]["dispatched"] is True
        assert len(audited) == 1
        assert audited[0]["actor"] == "safety_controller:fire_ventilation"

    @pytest.mark.asyncio
    async def test_broker_failure_is_audited_not_swallowed(self, ctl):
        audited = []

        async def dead_dispatch(**kwargs):
            return False

        actions = ctl.on_hazards([hazard("fire_risk")], timestamp=100.0)
        results = await execute_actions(
            actions, dispatch=dead_dispatch, audit=lambda **kw: audited.append(kw)
        )

        assert results[0]["dispatched"] is False
        assert audited[0]["outcome"] == "failed"
