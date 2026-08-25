from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, Optional

WINDOW_SIZE = 30
MIN_SAMPLES = 8
T_95 = {
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    12: 2.179, 15: 2.145, 20: 2.086, 25: 2.060, 30: 2.042,
}


def _t_critical(dof: int) -> float:
    if dof <= 0:
        return float("inf")
    for k in sorted(T_95):
        if dof <= k:
            return T_95[k]
    return 1.96


@dataclass
class Sample:
    t: float
    value: float


@dataclass
class Forecast:
    device_id: str
    property_name: str
    samples: int
    window_seconds: float
    slope_per_minute: float
    slope_ci_low: float
    slope_ci_high: float
    r_squared: float
    residual_sigma: float
    current_value: float
    horizon_minutes: float
    predicted_value: float
    predicted_ci_low: float
    predicted_ci_high: float
    trend: str
    significant: bool
    threshold: Optional[float] = None
    minutes_to_threshold: Optional[float] = None
    minutes_to_threshold_earliest: Optional[float] = None
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "property_name": self.property_name,
            "samples": self.samples,
            "window_seconds": round(self.window_seconds, 1),
            "slope_per_minute": round(self.slope_per_minute, 4),
            "slope_ci_95": [round(self.slope_ci_low, 4), round(self.slope_ci_high, 4)],
            "r_squared": round(self.r_squared, 3),
            "residual_sigma": round(self.residual_sigma, 4),
            "current_value": round(self.current_value, 3),
            "horizon_minutes": self.horizon_minutes,
            "predicted_value": round(self.predicted_value, 3),
            "predicted_ci_95": [
                round(self.predicted_ci_low, 3),
                round(self.predicted_ci_high, 3),
            ],
            "trend": self.trend,
            "significant": self.significant,
            "threshold": self.threshold,
            "minutes_to_threshold": (
                None
                if self.minutes_to_threshold is None
                else round(self.minutes_to_threshold, 1)
            ),
            "minutes_to_threshold_earliest": (
                None
                if self.minutes_to_threshold_earliest is None
                else round(self.minutes_to_threshold_earliest, 1)
            ),
            "note": self.note,
        }


@dataclass
class InsufficientData:
    device_id: str
    property_name: str
    samples: int
    required: int = MIN_SAMPLES

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "property_name": self.property_name,
            "samples": self.samples,
            "required": self.required,
            "trend": "unknown",
            "significant": False,
            "note": f"样本不足，需要至少 {self.required} 个点",
        }


@dataclass
class _Series:
    points: Deque[Sample] = field(default_factory=lambda: deque(maxlen=WINDOW_SIZE))


_series: dict[tuple[str, str], _Series] = {}


def reset() -> None:
    _series.clear()


def record(
    device_id: str,
    property_name: str,
    value: float,
    at: Optional[datetime] = None,
) -> None:
    moment = (at or datetime.now(timezone.utc)).timestamp()
    key = (device_id, property_name)
    _series.setdefault(key, _Series()).points.append(Sample(moment, float(value)))


def sample_count(device_id: str, property_name: str) -> int:
    series = _series.get((device_id, property_name))
    return len(series.points) if series else 0


def forecast(
    device_id: str,
    property_name: str,
    horizon_minutes: float = 10.0,
    threshold: Optional[float] = None,
):
    series = _series.get((device_id, property_name))
    count = len(series.points) if series else 0
    if count < MIN_SAMPLES:
        return InsufficientData(device_id, property_name, count)

    points = list(series.points)
    t0 = points[0].t
    xs = [(p.t - t0) / 60.0 for p in points]
    ys = [p.value for p in points]
    n = len(xs)

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return InsufficientData(device_id, property_name, count)

    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x

    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    ss_res = sum(r * r for r in residuals)
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    dof = n - 2
    sigma = math.sqrt(ss_res / dof) if dof > 0 else 0.0
    se_slope = sigma / math.sqrt(sxx) if sxx > 0 else 0.0
    t_crit = _t_critical(dof)

    slope_low = slope - t_crit * se_slope
    slope_high = slope + t_crit * se_slope
    significant = slope_low > 0 or slope_high < 0

    x_future = xs[-1] + horizon_minutes
    predicted = intercept + slope * x_future
    se_pred = (
        sigma * math.sqrt(1.0 + 1.0 / n + (x_future - mean_x) ** 2 / sxx)
        if sigma > 0
        else 0.0
    )
    pred_low = predicted - t_crit * se_pred
    pred_high = predicted + t_crit * se_pred

    if not significant:
        trend = "flat"
    elif slope > 0:
        trend = "rising"
    else:
        trend = "falling"

    current = ys[-1]
    minutes_to = None
    minutes_earliest = None
    if threshold is not None and significant:
        gap = threshold - current
        if (gap > 0 and slope > 0) or (gap < 0 and slope < 0):
            minutes_to = gap / slope
            fastest = slope_high if gap > 0 else slope_low
            if (gap > 0 and fastest > 0) or (gap < 0 and fastest < 0):
                minutes_earliest = gap / fastest

    if not significant:
        note = "斜率 95% 置信区间跨过 0，趋势不显著"
    elif r_squared < 0.5:
        note = f"趋势显著但拟合较差 (R²={r_squared:.2f})，数据波动大"
    else:
        note = "趋势显著"

    return Forecast(
        device_id=device_id,
        property_name=property_name,
        samples=n,
        window_seconds=points[-1].t - points[0].t,
        slope_per_minute=slope,
        slope_ci_low=slope_low,
        slope_ci_high=slope_high,
        r_squared=r_squared,
        residual_sigma=sigma,
        current_value=current,
        horizon_minutes=horizon_minutes,
        predicted_value=predicted,
        predicted_ci_low=pred_low,
        predicted_ci_high=pred_high,
        trend=trend,
        significant=significant,
        threshold=threshold,
        minutes_to_threshold=minutes_to,
        minutes_to_threshold_earliest=minutes_earliest,
        note=note,
    )


def tracked_series() -> list[dict]:
    return [
        {"device_id": device_id, "property_name": prop, "samples": len(s.points)}
        for (device_id, prop), s in sorted(_series.items())
    ]