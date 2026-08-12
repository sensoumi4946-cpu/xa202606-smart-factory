from analytics.anomaly_detector import AnomalyResult
from analytics.cross_subsystem_correlator import CrossSubsystemCorrelator


def _result(sensor_id, value, ts):
    return AnomalyResult(
        sensor_id=sensor_id,
        value=value,
        timestamp=ts,
        is_anomaly=True,
        z_score=5.0,
        reason="test",
        severity="critical",
    )


def test_fire_risk_pattern_fires_on_temp_and_co_together():
    corr = CrossSubsystemCorrelator(window_seconds=10.0)
    corr.push_anomaly(
        _result("sensor_dht22_01", 78.0, 1000.0),
        subsystem="temp_humidity", protocol="mqtt", property_name="temperature",
    )
    alerts = corr.push_anomaly(
        _result("sensor_mq2_01", 420.0, 1001.0),
        subsystem="gas", protocol="modbus", property_name="co_level",
    )
    assert len(alerts) == 1
    assert alerts[0].hypothesis.startswith("Simultaneous rise in CO and temperature")
    assert alerts[0].confidence == "high"
    assert set(alerts[0].subsystems_involved) == {"temp_humidity", "gas"}


def test_single_source_produces_no_alert():
    corr = CrossSubsystemCorrelator(window_seconds=10.0)
    alerts = corr.push_anomaly(
        _result("sensor_dht22_01", 78.0, 1000.0),
        subsystem="temp_humidity", protocol="mqtt", property_name="temperature",
    )
    assert alerts == []


def test_same_pair_not_re_emitted_within_window():
    corr = CrossSubsystemCorrelator(window_seconds=10.0)
    corr.push_anomaly(
        _result("sensor_dht22_01", 78.0, 1000.0),
        subsystem="temp_humidity", protocol="mqtt", property_name="temperature",
    )
    first = corr.push_anomaly(
        _result("sensor_mq2_01", 420.0, 1001.0),
        subsystem="gas", protocol="modbus", property_name="co_level",
    )
    assert len(first) == 1

    second = corr.push_anomaly(
        _result("sensor_mq2_01", 430.0, 1002.0),
        subsystem="gas", protocol="modbus", property_name="co_level",
    )
    assert second == []


def test_old_readings_are_pruned_outside_window():
    corr = CrossSubsystemCorrelator(window_seconds=10.0)
    corr.push_anomaly(
        _result("sensor_dht22_01", 78.0, 1000.0),
        subsystem="temp_humidity", protocol="mqtt", property_name="temperature",
    )
    alerts = corr.push_anomaly(
        _result("sensor_mq2_01", 420.0, 1015.0),
        subsystem="gas", protocol="modbus", property_name="co_level",
    )
    assert alerts == []


def test_three_unrelated_sensors_trigger_low_confidence_generic_alert():
    corr = CrossSubsystemCorrelator(window_seconds=10.0, min_sources=2)
    corr.push_anomaly(
        _result("sensor_a", 1.0, 1000.0),
        subsystem="lighting", protocol="rest", property_name="occupancy",
    )
    corr.push_anomaly(
        _result("sensor_b", 2.0, 1001.0),
        subsystem="counting", protocol="rest", property_name="count",
    )
    alerts = corr.push_anomaly(
        _result("sensor_c", 3.0, 1002.0),
        subsystem="agv", protocol="opcua", property_name="distance",
    )
    assert len(alerts) == 1
    assert alerts[0].confidence == "low"
    assert "3 sensors" in alerts[0].hypothesis
