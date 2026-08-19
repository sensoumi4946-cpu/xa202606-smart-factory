from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

MIN_POINTS = 4
MAX_POINTS = 30
MAX_HORIZON_S = 300.0
MIN_R_SQUARED = 0.55


@dataclass
class Prediction:
    device_id: str
    property_name: str
    current_value: float
    threshold: float
    slope_per_s: float
    seconds_to_threshold: Optional[float]
    r_squared: float
    confidence: str
    will_breach: bool
    message: str


THRESHOLDS: dict[str, tuple[float, str]] = {
    "temperature": (38.0, "above"),
    "co": (35.0, "above"),
    "smoke": (8.0, "above"),
    "combustible_gas": (3.0, "above"),
    "humidity": (85.0, "above"),
    "distance": (30.0, "below"),
}


def _linear_fit(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    n = len(points)
    mean_t = sum(p[0] for p in points) / n
    mean_v = sum(p[1] for p in points) / n

    sxx = sum((p[0] - mean_t) ** 2 for p in points)
    if sxx == 0.0:
        return 0.0, mean_v, 0.0

    sxy = sum((p[0] - mean_t) * (p[1] - mean_v) for p in points)
    slope = sxy / sxx
    intercept = mean_v - slope * mean_t

    syy = sum((p[1] - mean_v) ** 2 for p in points)
    if syy == 0.0:
        return slope, intercept, 1.0

    ss_res = sum((p[1] - (slope * p[0] + intercept)) ** 2 for p in points)
    r_squared = max(0.0, 1.0 - ss_res / syy)
    return slope, intercept, r_squared


def _confidence(r_squared: float, seconds: float) -> str:
    if r_squared >= 0.85 and seconds <= 60:
        return "high"
    if r_squared >= 0.70:
        return "medium"
    return "low"


class FaultPredictor:
    def __init__(
        self,
        thresholds: Optional[dict[str, tuple[float, str]]] = None,
        max_points: int = MAX_POINTS,
        max_horizon_s: float = MAX_HORIZON_S,
        min_r_squared: float = MIN_R_SQUARED,
    ) -> None:
        self.thresholds = dict(thresholds or THRESHOLDS)
        self.max_points = max_points
        self.max_horizon_s = max_horizon_s
        self.min_r_squared = min_r_squared
        self._series: dict[tuple[str, str], deque] = defaultdict(
            lambda: deque(maxlen=self.max_points)
        )

    def reset(self) -> None:
        self._series.clear()

    def push(
        self,
        device_id: str,
        property_name: str,
        value: float,
        timestamp: Optional[float] = None,
    ) -> Optional[Prediction]:
        prop = property_name.lower()
        if prop not in self.thresholds:
            return None

        ts = time.time() if timestamp is None else float(timestamp)
        key = (device_id, prop)
        self._series[key].append((ts, float(value)))
        points = list(self._series[key])

        if len(points) < MIN_POINTS:
            return None

        threshold, direction = self.thresholds[prop]
        slope, intercept, r_squared = _linear_fit(points)
        current = points[-1][1]

        breached_now = (
            current >= threshold if direction == "above" else current <= threshold
        )
        if breached_now:
            return Prediction(
                device_id=device_id,
                property_name=prop,
                current_value=current,
                threshold=threshold,
                slope_per_s=slope,
                seconds_to_threshold=0.0,
                r_squared=r_squared,
                confidence="high",
                will_breach=True,
                message=f"{prop} {current:.1f} already at or past {threshold:.1f}",
            )

        moving_toward = slope > 0 if direction == "above" else slope < 0
        if not moving_toward or abs(slope) < 1e-9:
            return None

        seconds = (threshold - current) / slope
        if seconds <= 0 or seconds > self.max_horizon_s:
            return None
        if r_squared < self.min_r_squared:
            return None

        return Prediction(
            device_id=device_id,
            property_name=prop,
            current_value=current,
            threshold=threshold,
            slope_per_s=slope,
            seconds_to_threshold=seconds,
            r_squared=r_squared,
            confidence=_confidence(r_squared, seconds),
            will_breach=True,
            message=(
                f"{prop} rising {slope:+.2f}/s — predicted to reach "
                f"{threshold:.1f} in {seconds:.0f}s"
            ),
        )

    def push_measurements(
        self,
        device_id: str,
        measurements: list[dict],
        timestamp: Optional[float] = None,
    ) -> list[Prediction]:
        out = []
        for m in measurements:
            value = m.get("value")
            prop = m.get("type") or m.get("property_name") or ""
            if value is None or not prop:
                continue
            try:
                pred = self.push(device_id, str(prop), float(value), timestamp)
            except (TypeError, ValueError):
                continue
            if pred is not None:
                out.append(pred)
        return out
