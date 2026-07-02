# Alert rule engine for the XA-202606 Smart Factory platform.
#
# RULES is a declarative list of alert conditions. evaluate() is a pure
# function that takes a Measurement and returns triggered alerts — it does
# not access the database. Rule evaluation is invoked inside
# store.insert_sensor_data() so that sensor insertion and alert insertion
# happen atomically in the same transaction.
from smart_factory_contracts.messages import Measurement, MeasurementType

RULES: list[dict] = [
    {
        "name": "high_temp",
        "type": MeasurementType.TEMPERATURE,
        "op": ">",
        "threshold": 38,
        "level": "warning",
    },
    {
        "name": "smoke_warning",
        "type": MeasurementType.SMOKE,
        "op": ">",
        "threshold": 8,
        "level": "warning",
    },
    {
        "name": "co_warning",
        "type": MeasurementType.CO,
        "op": ">",
        "threshold": 35,
        "level": "critical",
    },
    {
        "name": "gas_leak",
        "type": MeasurementType.COMBUSTIBLE_GAS,
        "op": ">",
        "threshold": 3,
        "level": "critical",
    },
    {
        "name": "agv_close",
        "type": MeasurementType.DISTANCE,
        "op": "<",
        "threshold": 30,
        "level": "warning",
    },
]


def evaluate(measurement: Measurement) -> list[dict]:
    """Return a list of triggered alert dicts for the given measurement."""
    results: list[dict] = []
    for rule in RULES:
        if measurement.type != rule["type"]:
            continue
        op = rule["op"]
        threshold = rule["threshold"]
        value = measurement.value
        triggered = False
        if op == ">" and value > threshold:
            triggered = True
        elif op == "<" and value < threshold:
            triggered = True
        if triggered:
            results.append(
                {
                    "rule_name": rule["name"],
                    "level": rule["level"],
                    "measurement_type": measurement.type.value,
                    "value": value,
                    "threshold": threshold,
                    "message": f"{measurement.type.value} {value} exceeds threshold {threshold}",
                }
            )
    return results
