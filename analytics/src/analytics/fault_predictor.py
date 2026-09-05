from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Optional

from analytics import trend_forecast
from analytics.thresholds import resolver

logger = logging.getLogger(__name__)

MIN_POINTS = 6
MAX_POINTS = 60
MAX_HORIZON_S = 3600.0
MIN_SPAN_S = 5.0


@dataclass
class Prediction:
    device_id: str
    property_name: str
    current_value: float
    threshold: float
    slope_per_s: float
    slope_ci_per_s: tuple[float, float]
    seconds_to_threshold: Optional[float]
    seconds_to_threshold_earliest: Optional[float]
    seconds_to_threshold_latest: Optional[float]
    r_squared: float
    samples: int
    window_seconds: float
    confidence: str
    will_breach: bool
    message: str

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "property_name": self.property_name,
            "current_value": round(self.current_value, 3),
            "threshold": self.threshold,
            "slope_per_s": round(self.slope_per_s, 6),
            "slope_ci_per_s": [
                round(self.slope_ci_per_s[0], 6),
                round(self.slope_ci_per_s[1], 6),
            ],
            "seconds_to_threshold": _round_opt(self.seconds_to_threshold),
            "seconds_to_threshold_earliest": _round_opt(
                self.seconds_to_threshold_earliest
            ),
            "seconds_to_threshold_latest": _round_opt(self.seconds_to_threshold_latest),
            "r_squared": round(self.r_squared, 3),
            "samples": self.samples,
            "window_seconds": round(self.window_seconds, 1),
            "confidence": self.confidence,
            "will_breach": self.will_breach,
            "message": self.message,
        }


def _round_opt(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 1)


def THRESHOLDS() -> dict[str, tuple[float, str]]:
    return resolver.thresholds()


def _confidence(fit, seconds: Optional[float], horizon: float) -> str:
    if seconds is None:
        return "low"
    width = fit.slope_ci_high - fit.slope_ci_low
    relative = abs(width / fit.slope) if fit.slope else float("inf")
    near = seconds <= horizon * 0.25
    if fit.r_squared >= 0.85 and relative <= 0.30 and near:
        return "high"
    if fit.r_squared >= 0.60 and relative <= 0.80:
        return "medium"
    return "low"


def _time_to(gap: float, rate: float) -> Optional[float]:
    if rate == 0.0:
        return None
    seconds = gap / rate
    return seconds if seconds > 0 else None


class FaultPredictor:
    def __init__(
        self,
        min_points: int = MIN_POINTS,
        max_points: int = MAX_POINTS,
        max_horizon_s: float = MAX_HORIZON_S,
        min_span_s: float = MIN_SPAN_S,
        thresholds: Optional[dict[str, tuple[float, str]]] = None,
    ) -> None:
        self.min_points = min_points
        self.max_horizon_s = max_horizon_s
        self.min_span_s = min_span_s
        self._override = thresholds
        self._series: dict[tuple[str, str], Deque[tuple[float, float]]] = defaultdict(
            lambda: deque(maxlen=max_points)
        )

    def reset(self) -> None:
        self._series.clear()

    def series_length(self, device_id: str, property_name: str) -> int:
        return len(self._series.get((device_id, property_name.lower()), ()))

    def tracked(self) -> list[dict]:
        return [
            {"device_id": d, "property_name": p, "samples": len(s)}
            for (d, p), s in sorted(self._series.items())
        ]

    def push(
        self,
        device_id: str,
        property_name: str,
        value: float,
        timestamp: Optional[float] = None,
    ) -> Optional[Prediction]:
        prop = property_name.lower()
        table = self._override if self._override is not None else resolver.thresholds()
        if prop not in table:
            return None

        ts = time.time() if timestamp is None else float(timestamp)
        key = (device_id, prop)
        self._series[key].append((ts, float(value)))
        points = list(self._series[key])

        threshold, direction = table[prop]
        current = points[-1][1]

        breached = (
            current >= threshold if direction == "above" else current <= threshold
        )
        if breached:
            return Prediction(
                device_id=device_id,
                property_name=prop,
                current_value=current,
                threshold=threshold,
                slope_per_s=0.0,
                slope_ci_per_s=(0.0, 0.0),
                seconds_to_threshold=0.0,
                seconds_to_threshold_earliest=0.0,
                seconds_to_threshold_latest=0.0,
                r_squared=1.0,
                samples=len(points),
                window_seconds=points[-1][0] - points[0][0],
                confidence="high",
                will_breach=True,
                message=f"{prop} {current:.1f} 已达到阈值 {threshold:.1f}",
            )

        if len(points) < self.min_points:
            return None

        span = points[-1][0] - points[0][0]
        if span < self.min_span_s:
            return None

        fitted = trend_forecast.fit(points, min_samples=self.min_points)
        if fitted is None:
            return None

        if not fitted.significant:
            return None

        moving_toward = fitted.slope > 0 if direction == "above" else fitted.slope < 0
        if not moving_toward:
            return None

        gap = threshold - current
        seconds = _time_to(gap, fitted.slope)
        if seconds is None or seconds > self.max_horizon_s:
            return None

        fastest = fitted.slope_ci_high if gap > 0 else fitted.slope_ci_low
        slowest = fitted.slope_ci_low if gap > 0 else fitted.slope_ci_high
        earliest = _time_to(gap, fastest)
        latest = _time_to(gap, slowest)
        if latest is not None and latest > self.max_horizon_s:
            latest = None

        confidence = _confidence(fitted, seconds, self.max_horizon_s)

        if earliest is not None and latest is not None:
            window = f"，95% 区间 {earliest:.0f}–{latest:.0f}s"
        elif earliest is not None:
            window = f"，最快 {earliest:.0f}s"
        else:
            window = ""

        return Prediction(
            device_id=device_id,
            property_name=prop,
            current_value=current,
            threshold=threshold,
            slope_per_s=fitted.slope,
            slope_ci_per_s=(fitted.slope_ci_low, fitted.slope_ci_high),
            seconds_to_threshold=seconds,
            seconds_to_threshold_earliest=earliest,
            seconds_to_threshold_latest=latest,
            r_squared=fitted.r_squared,
            samples=fitted.n,
            window_seconds=span,
            confidence=confidence,
            will_breach=True,
            message=(
                f"{prop} 以 {fitted.slope:+.3f}/s 变化，预计 {seconds:.0f}s 后"
                f"达到 {threshold:.1f}{window}"
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