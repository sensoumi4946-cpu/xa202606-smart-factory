from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

STOP_DISTANCE_CM = 15.0
SLOW_DISTANCE_CM = 30.0
REACTION_TIME_S = 0.35
DECELERATION_CM_S2 = 45.0
MIN_POINTS = 2
MAX_POINTS = 12
CLEAR_DISTANCE_CM = 60.0


@dataclass
class AgvDecision:
    device_id: str
    distance_cm: float
    closing_rate_cm_s: float
    time_to_impact_s: Optional[float]
    braking_distance_cm: float
    safe_margin_cm: float
    level: str
    action: Optional[str]
    reason: str

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "distance_cm": round(self.distance_cm, 1),
            "closing_rate_cm_s": round(self.closing_rate_cm_s, 2),
            "time_to_impact_s": (
                None if self.time_to_impact_s is None else round(self.time_to_impact_s, 2)
            ),
            "braking_distance_cm": round(self.braking_distance_cm, 1),
            "safe_margin_cm": round(self.safe_margin_cm, 1),
            "level": self.level,
            "action": self.action,
            "reason": self.reason,
        }


def braking_distance(speed_cm_s: float, deceleration: float, reaction_s: float) -> float:
    if speed_cm_s <= 0:
        return 0.0
    return speed_cm_s * reaction_s + (speed_cm_s ** 2) / (2.0 * deceleration)


class AgvGuard:
    def __init__(
        self,
        stop_distance_cm: float = STOP_DISTANCE_CM,
        slow_distance_cm: float = SLOW_DISTANCE_CM,
        clear_distance_cm: float = CLEAR_DISTANCE_CM,
        deceleration_cm_s2: float = DECELERATION_CM_S2,
        reaction_time_s: float = REACTION_TIME_S,
        max_points: int = MAX_POINTS,
    ) -> None:
        self.stop_distance_cm = stop_distance_cm
        self.slow_distance_cm = slow_distance_cm
        self.clear_distance_cm = clear_distance_cm
        self.deceleration_cm_s2 = deceleration_cm_s2
        self.reaction_time_s = reaction_time_s
        self._series: dict[str, deque] = defaultdict(lambda: deque(maxlen=max_points))
        self._state: dict[str, str] = defaultdict(lambda: "clear")

    def reset(self) -> None:
        self._series.clear()
        self._state.clear()

    def state_of(self, device_id: str) -> str:
        return self._state[device_id]

    def _closing_rate(self, device_id: str) -> float:
        points = list(self._series[device_id])
        if len(points) < MIN_POINTS:
            return 0.0
        (t0, d0), (t1, d1) = points[0], points[-1]
        dt = t1 - t0
        if dt <= 0:
            return 0.0
        return (d0 - d1) / dt

    def push_distance(
        self,
        device_id: str,
        distance_cm: float,
        timestamp: Optional[float] = None,
    ) -> AgvDecision:
        ts = time.time() if timestamp is None else float(timestamp)
        distance_cm = float(distance_cm)
        self._series[device_id].append((ts, distance_cm))

        closing = self._closing_rate(device_id)
        speed = max(0.0, closing)
        brake = braking_distance(speed, self.deceleration_cm_s2, self.reaction_time_s)
        margin = distance_cm - brake
        tti = distance_cm / speed if speed > 0.5 else None

        level = "clear"
        action = None
        reason = "path clear"

        if distance_cm <= self.stop_distance_cm:
            level = "stop"
            action = "stop"
            reason = f"obstacle at {distance_cm:.0f}cm, inside stop zone {self.stop_distance_cm:.0f}cm"
        elif margin <= 0 and speed > 0.5:
            level = "stop"
            action = "stop"
            reason = (
                f"closing {speed:.1f}cm/s needs {brake:.0f}cm to brake, "
                f"only {distance_cm:.0f}cm available"
            )
        elif distance_cm <= self.slow_distance_cm:
            level = "slow"
            action = "slow"
            reason = f"obstacle at {distance_cm:.0f}cm, inside slow zone {self.slow_distance_cm:.0f}cm"
        elif tti is not None and tti <= 3.0:
            level = "slow"
            action = "slow"
            reason = f"closing {speed:.1f}cm/s, impact in {tti:.1f}s"

        previous = self._state[device_id]

        if level == "clear" and previous != "clear":
            if distance_cm >= self.clear_distance_cm:
                self._state[device_id] = "clear"
                return AgvDecision(
                    device_id=device_id,
                    distance_cm=distance_cm,
                    closing_rate_cm_s=closing,
                    time_to_impact_s=tti,
                    braking_distance_cm=brake,
                    safe_margin_cm=margin,
                    level="clear",
                    action="resume",
                    reason=f"path clear at {distance_cm:.0f}cm",
                )
            level = previous
            action = None
            reason = f"holding {previous} until {self.clear_distance_cm:.0f}cm"

        decision = AgvDecision(
            device_id=device_id,
            distance_cm=distance_cm,
            closing_rate_cm_s=closing,
            time_to_impact_s=tti,
            braking_distance_cm=brake,
            safe_margin_cm=margin,
            level=level,
            action=action if level != previous else None,
            reason=reason,
        )
        self._state[device_id] = level
        return decision

    def push_measurements(
        self,
        device_id: str,
        measurements: list[dict],
        timestamp: Optional[float] = None,
    ) -> Optional[AgvDecision]:
        for m in measurements:
            prop = str(m.get("type") or m.get("property_name") or "").lower()
            if prop != "distance":
                continue
            value = m.get("value")
            if value is None:
                continue
            try:
                return self.push_distance(device_id, float(value), timestamp)
            except (TypeError, ValueError):
                return None
        return None
