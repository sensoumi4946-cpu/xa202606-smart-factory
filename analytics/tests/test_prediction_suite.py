import pytest

from analytics.agv_guard import AgvGuard, braking_distance
from analytics.fault_predictor import FaultPredictor
from analytics.hazard_reasoner import HazardReasoner


class TestFaultPredictor:
    def setup_method(self):
        self.p = FaultPredictor()

    def test_no_prediction_before_enough_points(self):
        assert self.p.push("d1", "temperature", 20.0, timestamp=0.0) is None
        assert self.p.push("d1", "temperature", 21.0, timestamp=1.0) is None
        assert self.p.push("d1", "temperature", 22.0, timestamp=2.0) is None

    def test_predicts_time_to_threshold(self):
        for i in range(6):
            pred = self.p.push("d1", "temperature", 20.0 + i * 2.0, timestamp=float(i))
        assert pred is not None
        assert pred.will_breach
        assert pred.slope_per_s == pytest.approx(2.0, abs=0.01)
        assert pred.seconds_to_threshold == pytest.approx(4.0, abs=0.2)
        assert pred.confidence == "high"

    def test_stable_signal_gives_no_prediction(self):
        pred = None
        for i in range(10):
            pred = self.p.push("d1", "temperature", 22.0, timestamp=float(i))
        assert pred is None

    def test_falling_value_does_not_predict_upper_breach(self):
        pred = None
        for i in range(8):
            pred = self.p.push("d1", "temperature", 30.0 - i, timestamp=float(i))
        assert pred is None

    def test_distance_uses_below_direction(self):
        pred = None
        for i in range(8):
            pred = self.p.push("agv1", "distance", 100.0 - i * 8.0, timestamp=float(i))
        assert pred is not None
        assert pred.seconds_to_threshold is not None
        assert pred.slope_per_s < 0

    def test_already_breached_reports_zero(self):
        for i in range(5):
            self.p.push("d1", "co", 10.0 + i, timestamp=float(i))
        pred = self.p.push("d1", "co", 90.0, timestamp=6.0)
        assert pred is not None
        assert pred.seconds_to_threshold == 0.0

    def test_far_future_breach_is_ignored(self):
        pred = None
        for i in range(10):
            pred = self.p.push("d1", "temperature", 20.0 + i * 0.001, timestamp=float(i))
        assert pred is None

    def test_noisy_trend_rejected_by_r_squared(self):
        values = [20.0, 35.0, 21.0, 34.0, 22.0, 36.0, 23.0, 33.0]
        pred = None
        for i, v in enumerate(values):
            pred = self.p.push("d1", "temperature", v, timestamp=float(i))
        assert pred is None or pred.r_squared >= 0.55

    def test_unknown_property_ignored(self):
        assert self.p.push("d1", "voltage", 999.0) is None

    def test_devices_are_independent(self):
        for i in range(6):
            self.p.push("hot", "temperature", 20.0 + i * 2.0, timestamp=float(i))
        pred = None
        for i in range(6):
            pred = self.p.push("cool", "temperature", 20.0, timestamp=float(i))
        assert pred is None


class TestHazardReasoner:
    def setup_method(self):
        self.r = HazardReasoner()

    def test_fire_risk_needs_both_signals(self):
        alerts = self.r.observe(
            "mq2", "gas", "modbus", [{"type": "co", "value": 50.0}], timestamp=100.0
        )
        assert alerts == []

        alerts = self.r.observe(
            "dht22",
            "temp_humidity",
            "mqtt",
            [{"type": "temperature", "value": 45.0}],
            timestamp=102.0,
        )
        assert len(alerts) == 1
        assert alerts[0].rule_name == "fire_risk"
        assert alerts[0].severity == "critical"

    def test_alert_records_both_protocols(self):
        self.r.observe("mq2", "gas", "modbus", [{"type": "co", "value": 50.0}], timestamp=100.0)
        alerts = self.r.observe(
            "dht22",
            "temp_humidity",
            "mqtt",
            [{"type": "temperature", "value": 45.0}],
            timestamp=101.0,
        )
        assert alerts[0].protocols == ["modbus", "mqtt"]
        assert alerts[0].subsystems == ["gas", "temp_humidity"]

    def test_chain_describes_causal_evidence(self):
        self.r.observe("mq2", "gas", "modbus", [{"type": "co", "value": 50.0}], timestamp=100.0)
        alerts = self.r.observe(
            "dht22",
            "temp_humidity",
            "mqtt",
            [{"type": "temperature", "value": 45.0}],
            timestamp=101.0,
        )
        chain = alerts[0].chain()
        assert len(chain) == 2
        assert any("MODBUS" in c for c in chain)
        assert any("MQTT" in c for c in chain)

    def test_stale_evidence_does_not_trigger(self):
        self.r.observe("mq2", "gas", "modbus", [{"type": "co", "value": 50.0}], timestamp=0.0)
        alerts = self.r.observe(
            "dht22",
            "temp_humidity",
            "mqtt",
            [{"type": "temperature", "value": 45.0}],
            timestamp=500.0,
        )
        assert alerts == []

    def test_cooldown_prevents_alert_flood(self):
        first = self.r.observe(
            "both",
            "gas",
            "modbus",
            [{"type": "co", "value": 50.0}, {"type": "temperature", "value": 45.0}],
            timestamp=100.0,
        )
        second = self.r.observe(
            "both",
            "gas",
            "modbus",
            [{"type": "co", "value": 51.0}, {"type": "temperature", "value": 46.0}],
            timestamp=102.0,
        )
        assert len(first) == 1
        assert second == []

    def test_refires_after_cooldown(self):
        self.r.observe(
            "both",
            "gas",
            "modbus",
            [{"type": "co", "value": 50.0}, {"type": "temperature", "value": 45.0}],
            timestamp=100.0,
        )
        later = self.r.observe(
            "both",
            "gas",
            "modbus",
            [{"type": "co", "value": 50.0}, {"type": "temperature", "value": 45.0}],
            timestamp=200.0,
        )
        assert len(later) == 1

    def test_gas_leak_requires_no_occupancy(self):
        alerts = self.r.observe(
            "mix",
            "gas",
            "modbus",
            [{"type": "combustible_gas", "value": 6.0}, {"type": "occupancy", "value": 1.0}],
            timestamp=10.0,
        )
        assert all(a.rule_name != "gas_leak_unattended" for a in alerts)

        self.r.reset()
        alerts = self.r.observe(
            "mix",
            "gas",
            "modbus",
            [{"type": "combustible_gas", "value": 6.0}, {"type": "occupancy", "value": 0.0}],
            timestamp=10.0,
        )
        assert any(a.rule_name == "gas_leak_unattended" for a in alerts)

    def test_normal_readings_produce_nothing(self):
        alerts = self.r.observe(
            "dht22",
            "temp_humidity",
            "mqtt",
            [{"type": "temperature", "value": 24.0}, {"type": "humidity", "value": 50.0}],
            timestamp=10.0,
        )
        assert alerts == []

    def test_to_dict_is_serialisable(self):
        import json

        self.r.observe("mq2", "gas", "modbus", [{"type": "co", "value": 50.0}], timestamp=100.0)
        alerts = self.r.observe(
            "dht22",
            "temp_humidity",
            "mqtt",
            [{"type": "temperature", "value": 45.0}],
            timestamp=101.0,
        )
        json.dumps(alerts[0].to_dict())


class TestAgvGuard:
    def setup_method(self):
        self.g = AgvGuard()

    def test_braking_distance_grows_with_speed(self):
        assert braking_distance(0.0, 45.0, 0.35) == 0.0
        slow = braking_distance(10.0, 45.0, 0.35)
        fast = braking_distance(40.0, 45.0, 0.35)
        assert fast > slow > 0

    def test_far_and_still_is_clear(self):
        d = self.g.push_distance("agv1", 200.0, timestamp=0.0)
        assert d.level == "clear"
        assert d.action is None

    def test_inside_stop_zone_commands_stop(self):
        self.g.push_distance("agv1", 200.0, timestamp=0.0)
        d = self.g.push_distance("agv1", 10.0, timestamp=1.0)
        assert d.level == "stop"
        assert d.action == "stop"

    def test_inside_slow_zone_commands_slow(self):
        self.g.push_distance("agv1", 40.0, timestamp=0.0)
        d = self.g.push_distance("agv1", 25.0, timestamp=1.0)
        assert d.level == "slow"
        assert d.action == "slow"

    def test_fast_approach_stops_before_stop_zone(self):
        self.g.push_distance("agv1", 300.0, timestamp=0.0)
        d = self.g.push_distance("agv1", 120.0, timestamp=1.0)
        assert d.closing_rate_cm_s == pytest.approx(180.0, abs=1.0)
        assert d.braking_distance_cm > 120.0
        assert d.level == "stop"

    def test_slow_approach_far_away_stays_clear(self):
        self.g.push_distance("agv1", 300.0, timestamp=0.0)
        d = self.g.push_distance("agv1", 298.0, timestamp=1.0)
        assert d.level == "clear"

    def test_time_to_impact_is_computed(self):
        self.g.push_distance("agv1", 100.0, timestamp=0.0)
        d = self.g.push_distance("agv1", 80.0, timestamp=1.0)
        assert d.time_to_impact_s == pytest.approx(4.0, abs=0.1)

    def test_repeat_level_does_not_repeat_action(self):
        self.g.push_distance("agv1", 40.0, timestamp=0.0)
        first = self.g.push_distance("agv1", 25.0, timestamp=1.0)
        second = self.g.push_distance("agv1", 24.0, timestamp=2.0)
        assert first.action == "slow"
        assert second.action is None

    def test_hysteresis_prevents_premature_resume(self):
        self.g.push_distance("agv1", 40.0, timestamp=0.0)
        self.g.push_distance("agv1", 25.0, timestamp=1.0)
        held = self.g.push_distance("agv1", 45.0, timestamp=2.0)
        assert held.action is None
        assert self.g.state_of("agv1") == "slow"

    def test_resume_once_fully_clear(self):
        self.g.push_distance("agv1", 40.0, timestamp=0.0)
        self.g.push_distance("agv1", 25.0, timestamp=1.0)
        resumed = self.g.push_distance("agv1", 80.0, timestamp=2.0)
        assert resumed.action == "resume"
        assert resumed.level == "clear"

    def test_ignores_non_distance_measurements(self):
        assert self.g.push_measurements("agv1", [{"type": "temperature", "value": 25.0}]) is None

    def test_push_measurements_reads_distance(self):
        d = self.g.push_measurements("agv1", [{"type": "distance", "value": 10.0}])
        assert d is not None
        assert d.level == "stop"

    def test_devices_tracked_separately(self):
        self.g.push_distance("agv1", 40.0, timestamp=0.0)
        self.g.push_distance("agv1", 10.0, timestamp=1.0)
        d = self.g.push_distance("agv2", 200.0, timestamp=1.0)
        assert d.level == "clear"
        assert self.g.state_of("agv1") == "stop"
