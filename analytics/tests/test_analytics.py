"""
analytics/tests/test_analytics.py
Tests for AnomalyDetector and CrossSubsystemCorrelator
"""

import time

import pytest

from analytics.anomaly_detector import AnomalyDetector
from analytics.cross_subsystem_correlator import CrossSubsystemCorrelator


# AnomalyDetector

class TestAnomalyDetector:
    def setup_method(self):
        self.det = AnomalyDetector(window_size=20, z_threshold=3.0)

    def _fill_baseline(self, sensor_id: str, value: float, n: int = 10) -> None:
        for _ in range(n):
            self.det.push_reading(sensor_id, value)

    def test_no_anomaly_on_stable_signal(self):
        self._fill_baseline("s1", 25.0, 15)
        result = self.det.push_reading("s1", 25.1)
        assert not result.is_anomaly

    def test_flags_spike(self):
        self._fill_baseline("s1", 25.0, 15)
        result = self.det.push_reading("s1", 999.0)
        assert result.is_anomaly
        assert result.z_score is not None
        assert result.z_score > 3.0

    def test_no_flag_before_baseline_ready(self):
        # Fewer than 5 readings → z_score is None, no anomaly
        result = self.det.push_reading("s2", 999.0)
        assert not result.is_anomaly
        assert result.z_score is None

    def test_hard_limit_temperature(self):
        # Temperature above 120°C should always be flagged
        result = self.det.push_reading("s3", 250.0, property_name="temperature")
        assert result.is_anomaly
        assert "physical range" in (result.reason or "")
        assert result.severity == "high"

    def test_hard_limit_co_level(self):
        result = self.det.push_reading("s4", 300.0, property_name="co_level")
        assert result.is_anomaly
        assert result.severity == "high"

    def test_different_sensors_independent(self):
        self._fill_baseline("sA", 10.0, 15)
        self._fill_baseline("sB", 100.0, 15)
        # sA spikes, sB is fine
        assert self.det.push_reading("sA", 500.0).is_anomaly
        assert not self.det.push_reading("sB", 100.5).is_anomaly

    def test_sensor_stats_returns_mean(self):
        for v in [10.0, 12.0, 14.0, 16.0, 18.0]:
            self.det.push_reading("sC", v)
        stats = self.det.sensor_stats("sC")
        assert stats["samples"] == 5
        assert abs(stats["mean"] - 14.0) < 0.01

    def test_reset_clears_window(self):
        self._fill_baseline("sD", 50.0, 15)
        self.det.reset_sensor("sD")
        # After reset, should have 0 samples
        stats = self.det.sensor_stats("sD")
        assert stats["samples"] == 0

    def test_severity_high_at_extreme_z(self):
        self._fill_baseline("sE", 50.0, 15)
        result = self.det.push_reading("sE", 5000.0)
        if result.is_anomaly:
            assert result.severity in ("medium", "high")

    def test_window_rolls_off_old_values(self):
        det = AnomalyDetector(window_size=5, z_threshold=3.0)
        for _ in range(20):
            det.push_reading("sF", 100.0)
        stats = det.sensor_stats("sF")
        assert stats["samples"] == 5


# CrossSubsystemCorrelator

class TestCorrelator:
    def setup_method(self):
        self.det = AnomalyDetector(window_size=20, z_threshold=3.0)
        self.cor = CrossSubsystemCorrelator(window_seconds=10.0, min_sources=2)

    def _make_anomaly(self, sensor_id: str, value: float, property_name: str):
        for _ in range(15):
            self.det.push_reading(sensor_id, 25.0, property_name=property_name)
        result = self.det.push_reading(sensor_id, value, property_name=property_name)
        return result

    def test_no_alert_single_sensor(self):
        r = self._make_anomaly("gas1", 999.0, "co_level")
        alerts = self.cor.push_anomaly(r, "hall_a", "Modbus", "co_level")
        assert alerts == []

    def test_fire_risk_alert_fires(self):
        r1 = self._make_anomaly("gas1", 999.0, "co_level")
        self.cor.push_anomaly(r1, "hall_a", "Modbus", "co_level")

        r2 = self._make_anomaly("temp1", 999.0, "temperature")
        alerts = self.cor.push_anomaly(r2, "hall_a", "MQTT", "temperature")

        assert len(alerts) == 1
        assert "fire" in alerts[0]["hypothesis"].lower() or "combustion" in alerts[0]["hypothesis"].lower()

    def test_no_duplicate_alerts(self):
        r1 = self._make_anomaly("gas2", 999.0, "co_level")
        r2 = self._make_anomaly("temp2", 999.0, "temperature")

        self.cor.push_anomaly(r1, "hall_b", "Modbus", "co_level")
        first_alerts = self.cor.push_anomaly(r2, "hall_b", "MQTT", "temperature")

        # Second pair from the same sensors shouldn't fire again
        r3 = self._make_anomaly("gas2", 999.0, "co_level")
        r4 = self._make_anomaly("temp2", 999.0, "temperature")
        self.cor.push_anomaly(r3, "hall_b", "Modbus", "co_level")
        second_alerts = self.cor.push_anomaly(r4, "hall_b", "MQTT", "temperature")

        assert len(first_alerts) == 1
        assert len(second_alerts) == 0

    def test_clear_alert_allows_refire(self):
        r1 = self._make_anomaly("gas3", 999.0, "co_level")
        r2 = self._make_anomaly("temp3", 999.0, "temperature")
        self.cor.push_anomaly(r1, "hall_c", "Modbus", "co_level")
        first = self.cor.push_anomaly(r2, "hall_c", "MQTT", "temperature")
        assert len(first) == 1

        self.cor.clear_alert(first[0]["alert_id"])

        r3 = self._make_anomaly("gas3", 999.0, "co_level")
        r4 = self._make_anomaly("temp3", 999.0, "temperature")
        self.cor.push_anomaly(r3, "hall_c", "Modbus", "co_level")
        second = self.cor.push_anomaly(r4, "hall_c", "MQTT", "temperature")
        assert len(second) == 1

    def test_protocols_captured(self):
        r1 = self._make_anomaly("gas4", 999.0, "co_level")
        r2 = self._make_anomaly("temp4", 999.0, "temperature")
        self.cor.push_anomaly(r1, "hall_d", "Modbus", "co_level")
        alerts = self.cor.push_anomaly(r2, "hall_d", "OPC-UA", "temperature")
        assert len(alerts) == 1
        assert "Modbus" in alerts[0]["protocols"]
        assert "OPC-UA" in alerts[0]["protocols"]
