"""
analytics/anomaly_detector.py
Statistical anomaly detection for individual sensor streams.
"""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_WINDOW = 30

DEFAULT_THRESHOLD = 3.0


@dataclass
class AnomalyResult:
    sensor_id: str
    value: float
    timestamp: float
    is_anomaly: bool
    z_score: Optional[float]   
    reason: Optional[str]     
    severity: str             


@dataclass
class SensorWindow:

    sensor_id: str
    max_size: int = DEFAULT_WINDOW
    values: deque = field(default_factory=deque)

    def push(self, value: float) -> None:
        self.values.append(value)
        if len(self.values) > self.max_size:
            self.values.popleft()

    @property
    def mean(self) -> float:
        return sum(self.values) / len(self.values)

    @property
    def std(self) -> float:
        if len(self.values) < 2:
            return 0.0
        m = self.mean
        variance = sum((v - m) ** 2 for v in self.values) / (len(self.values) - 1)
        return math.sqrt(variance)

    def z_score(self, value: float) -> Optional[float]:
        if len(self.values) < 5:
            return None
        s = self.std
        if s == 0:
            return 0.0
        return (value - self.mean) / s


# Physical limits per sensor type.
_HARD_LIMITS: dict[str, tuple[float, float]] = {
    "temperature": (-40.0, 120.0),  # °C
    "current": (0.0, 500.0),        # A
    "co_level": (0.0, 200.0),       # ppm
    "vibration": (0.0, 50.0),       # mm/s
    "pressure": (0.0, 10.0),        # bar
    "voltage": (0.0, 1000.0),       # V
}


def _severity_from_z(z: float) -> str:
    abs_z = abs(z)
    if abs_z >= 5:
        return "high"
    if abs_z >= 4:
        return "medium"
    return "low"


class AnomalyDetector:

    def __init__(
        self,
        window_size: int = DEFAULT_WINDOW,
        z_threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        self.window_size = window_size
        self.z_threshold = z_threshold
        self._windows: dict[str, SensorWindow] = {}

    def _get_window(self, sensor_id: str) -> SensorWindow:
        if sensor_id not in self._windows:
            self._windows[sensor_id] = SensorWindow(
                sensor_id=sensor_id,
                max_size=self.window_size,
            )
        return self._windows[sensor_id]

    def push_reading(
        self,
        sensor_id: str,
        value: float,
        property_name: str = "",
        timestamp: Optional[float] = None,
    ) -> AnomalyResult:
        ts = timestamp or time.time()
        window = self._get_window(sensor_id)

        limits = _HARD_LIMITS.get(property_name)
        if limits is not None:
            lo, hi = limits
            if not (lo <= value <= hi):
                window.push(value)
                return AnomalyResult(
                    sensor_id=sensor_id,
                    value=value,
                    timestamp=ts,
                    is_anomaly=True,
                    z_score=None,
                    reason=(
                        f"Value {value} is outside physical range "
                        f"[{lo}, {hi}] for {property_name}"
                    ),
                    severity="high",
                )

        z = window.z_score(value)
        window.push(value)

        if z is None:
            return AnomalyResult(
                sensor_id=sensor_id,
                value=value,
                timestamp=ts,
                is_anomaly=False,
                z_score=None,
                reason="Collecting baseline data",
                severity="low",
            )

        is_anomaly = abs(z) >= self.z_threshold

        return AnomalyResult(
            sensor_id=sensor_id,
            value=value,
            timestamp=ts,
            is_anomaly=is_anomaly,
            z_score=round(z, 3),
            reason=(
                f"Z-score {z:.2f} exceeds threshold ±{self.z_threshold}"
                if is_anomaly
                else None
            ),
            severity=_severity_from_z(z) if is_anomaly else "low",
        )

    def sensor_stats(self, sensor_id: str) -> dict:
        if sensor_id not in self._windows:
            return {"sensor_id": sensor_id, "samples": 0}
        w = self._windows[sensor_id]
        return {
            "sensor_id": sensor_id,
            "samples": len(w.values),
            "mean": round(w.mean, 4) if w.values else None,
            "std": round(w.std, 4) if w.values else None,
            "window_size": self.window_size,
        }

    def reset_sensor(self, sensor_id: str) -> None:
        self._windows.pop(sensor_id, None)
