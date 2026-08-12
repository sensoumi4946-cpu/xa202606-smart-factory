from smart_factory_contracts.messages import Measurement, MeasurementType, Unit
from backend.rules import evaluate


def test_no_alert_below_threshold():
    m = Measurement(type=MeasurementType.TEMPERATURE, value=20.0, unit=Unit.CELSIUS)
    assert evaluate(m) == []


def test_high_temp_triggers_warning():
    m = Measurement(type=MeasurementType.TEMPERATURE, value=39.0, unit=Unit.CELSIUS)
    alerts = evaluate(m)
    assert len(alerts) == 1
    assert alerts[0]["rule_name"] == "high_temp"
    assert alerts[0]["level"] == "warning"


def test_co_triggers_critical():
    m = Measurement(type=MeasurementType.CO, value=40.0, unit=Unit.PPM)
    alerts = evaluate(m)
    assert len(alerts) == 1
    assert alerts[0]["rule_name"] == "co_warning"
    assert alerts[0]["level"] == "critical"


def test_agv_close_triggers_on_low_distance():
    m = Measurement(type=MeasurementType.DISTANCE, value=10.0, unit=Unit.CM)
    alerts = evaluate(m)
    assert len(alerts) == 1
    assert alerts[0]["rule_name"] == "agv_close"


def test_agv_far_does_not_trigger():
    m = Measurement(type=MeasurementType.DISTANCE, value=200.0, unit=Unit.CM)
    assert evaluate(m) == []


def test_boundary_value_does_not_trigger():
    m = Measurement(type=MeasurementType.TEMPERATURE, value=38.0, unit=Unit.CELSIUS)
    assert evaluate(m) == []


def test_unrelated_measurement_type_produces_no_alert():
    m = Measurement(type=MeasurementType.COUNT, value=99999.0, unit=Unit.COUNT)
    assert evaluate(m) == []
