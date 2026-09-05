

from analytics.thresholds import resolver
from smart_factory_contracts.messages import Measurement, MeasurementType

RULE_METADATA: dict[MeasurementType, tuple[str, str]] = {
    MeasurementType.TEMPERATURE: ("high_temp", "warning"),
    MeasurementType.SMOKE: ("smoke_warning", "warning"),
    MeasurementType.CO: ("co_warning", "critical"),
    MeasurementType.COMBUSTIBLE_GAS: ("gas_leak", "critical"),
    MeasurementType.DISTANCE: ("agv_close", "warning"),
}


def evaluate(measurement: Measurement) -> list[dict]:
    metadata = RULE_METADATA.get(measurement.type)
    resolved = resolver.threshold_for(measurement.type.value)
    if metadata is None or resolved is None:
        return []

    name, level = metadata
    threshold, direction = resolved
    value = measurement.value
    triggered = value > threshold if direction == "above" else value < threshold
    if not triggered:
        return []

    comparison = "above" if direction == "above" else "below"
    return [
        {
            "rule_name": name,
            "level": level,
            "measurement_type": measurement.type.value,
            "value": value,
            "threshold": threshold,
            "message": (
                f"{measurement.type.value} {value} is {comparison} "
                f"threshold {threshold}"
            ),
            "threshold_source": resolver.resolve_source(measurement.type.value),
        }
    ]
