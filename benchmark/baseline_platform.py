# A conventional, non-semantic IoT platform — the comparison baseline

from __future__ import annotations

from typing import Any, Optional

SUPPORTED_PROPERTIES = (
    "temperature",
    "humidity",
    "co",
    "smoke",
    "combustible_gas",
    "distance",
    "count",
    "occupancy",
    "light_state",
)

UNITS = {
    "temperature": "celsius",
    "humidity": "percent",
    "co": "ppm",
    "smoke": "ppm",
    "combustible_gas": "ppm",
    "distance": "cm",
    "count": "count",
    "occupancy": "boolean",
    "light_state": "boolean",
}

LIMITS = {
    "temperature": (-40.0, 80.0),
    "humidity": (0.0, 100.0),
    "co": (0.0, 1000.0),
    "smoke": (0.0, 1000.0),
    "combustible_gas": (0.0, 1000.0),
    "distance": (0.0, 450.0),
    "count": (0.0, 1_000_000.0),
    "occupancy": (0.0, 1.0),
    "light_state": (0.0, 1.0),
}

THRESHOLDS = {
    "temperature": 38.0,
    "co": 35.0,
    "smoke": 8.0,
    "combustible_gas": 3.0,
    "humidity": 85.0,
}

DASHBOARD_FIELDS = [
    {"key": "temperature", "label": "温度", "unit": "°C", "widget": "gauge"},
    {"key": "humidity", "label": "湿度", "unit": "%", "widget": "gauge"},
    {"key": "co", "label": "一氧化碳", "unit": "ppm", "widget": "line"},
    {"key": "smoke", "label": "烟雾", "unit": "ppm", "widget": "line"},
    {"key": "combustible_gas", "label": "可燃气体", "unit": "ppm", "widget": "line"},
    {"key": "distance", "label": "距离", "unit": "cm", "widget": "gauge"},
    {"key": "count", "label": "计数", "unit": "件", "widget": "number"},
    {"key": "occupancy", "label": "有人", "unit": "", "widget": "boolean"},
    {"key": "light_state", "label": "照明", "unit": "", "widget": "boolean"},
]


def validate_reading(property_name: str, value: float, unit: str) -> tuple[bool, str]:
    if property_name not in SUPPORTED_PROPERTIES:
        return False, f"unknown property '{property_name}'"
    if UNITS[property_name] != unit:
        return False, f"expected unit {UNITS[property_name]}, got {unit}"
    lo, hi = LIMITS[property_name]
    if not lo <= value <= hi:
        return False, f"{value} outside [{lo}, {hi}]"
    return True, "ok"


def evaluate_threshold(property_name: str, value: float) -> Optional[str]:
    if property_name == "temperature" and value > THRESHOLDS["temperature"]:
        return "high_temp"
    elif property_name == "co" and value > THRESHOLDS["co"]:
        return "co_warning"
    elif property_name == "smoke" and value > THRESHOLDS["smoke"]:
        return "smoke_detected"
    elif property_name == "combustible_gas" and value > THRESHOLDS["combustible_gas"]:
        return "gas_leak"
    elif property_name == "humidity" and value > THRESHOLDS["humidity"]:
        return "high_humidity"
    return None


def dashboard_config() -> list[dict[str, Any]]:
    return DASHBOARD_FIELDS


# What adding one new sensor type (vibration) costs on this platform.
EXTENSION_DIFF = [
    {"file": "baseline_platform.py:SUPPORTED_PROPERTIES", "lines": 1, "what": "register the name"},
    {"file": "baseline_platform.py:UNITS", "lines": 1, "what": "unit mapping"},
    {"file": "baseline_platform.py:LIMITS", "lines": 1, "what": "physical range"},
    {"file": "baseline_platform.py:THRESHOLDS", "lines": 1, "what": "alarm threshold"},
    {"file": "baseline_platform.py:evaluate_threshold", "lines": 2, "what": "new elif branch"},
    {"file": "baseline_platform.py:DASHBOARD_FIELDS", "lines": 1, "what": "widget definition"},
    {"file": "contracts/messages.py:MeasurementType", "lines": 1, "what": "enum member"},
    {"file": "contracts/messages.py:Unit", "lines": 1, "what": "enum member"},
    {"file": "dashboard/DashboardView.vue", "lines": 14, "what": "chart panel markup + binding"},
    {"file": "dashboard/api.ts", "lines": 3, "what": "type definition"},
    {"file": "analytics/anomaly_detector.py:_HARD_LIMITS", "lines": 1, "what": "detector range"},
    {"file": "analytics/fault_predictor.py:THRESHOLDS", "lines": 1, "what": "prediction target"},
    {"file": "tests/test_contracts.py", "lines": 8, "what": "new enum coverage"},
    {"file": "tests/test_baseline.py", "lines": 12, "what": "validation + threshold cases"},
]
