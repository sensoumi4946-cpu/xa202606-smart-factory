from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from analytics.anomaly_detector import AnomalyResult

logger = logging.getLogger(__name__)

DEFAULT_CORRELATION_WINDOW = 10.0

DEFAULT_MIN_SOURCES = 2


@dataclass
class CorrelatedAlert:
    alert_id: str
    triggered_at: float
    sources: list[dict]        # list of {sensor_id, subsystem, protocol, value}
    hypothesis: str            
    confidence: str            
    subsystems_involved: list[str]
    protocols_involved: list[str]


# Known multi-sensor patterns and what they might mean.
_PATTERNS: list[dict] = [
    {
        "name": "fire_risk",
        "required_properties": {"co_level", "temperature"},
        "hypothesis": "Simultaneous rise in CO and temperature — possible fire or combustion event",
        "confidence": "high",
    },
    {
        "name": "electrical_fault",
        "required_properties": {"current", "voltage"},
        "hypothesis": "Correlated current and voltage anomalies — possible electrical fault or arc",
        "confidence": "high",
    },
    {
        "name": "mechanical_stress",
        "required_properties": {"vibration", "temperature"},
        "hypothesis": "Vibration and temperature rising together — possible bearing or motor issue",
        "confidence": "medium",
    },
    {
        "name": "pressure_event",
        "required_properties": {"pressure", "temperature"},
        "hypothesis": "Pressure and temperature anomalies — check relief valves and seals",
        "confidence": "medium",
    },
]


def _match_pattern(property_names: set[str]) -> Optional[dict]:
    for pattern in _PATTERNS:
        if pattern["required_properties"].issubset(property_names):
            return pattern
    return None


class CrossSubsystemCorrelator:
    """
    It is fed AnomalyResult objects as they arrive.  It maintains a sliding
    window and emits CorrelatedAlert objects when it detects multi-source
    anomaly clusters.
    """

    def __init__(
        self,
        window_seconds: float = DEFAULT_CORRELATION_WINDOW,
        min_sources: int = DEFAULT_MIN_SOURCES,
    ) -> None:
        self.window_seconds = window_seconds
        self.min_sources = min_sources
        # Each entry: {sensor_id, subsystem, protocol, property_name, value, ts}
        self._recent: list[dict] = []
        self._emitted_ids: set[str] = set()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        self._recent = [e for e in self._recent if e["ts"] >= cutoff]

    def push_anomaly(
        self,
        result: AnomalyResult,
        subsystem: str,
        protocol: str,
        property_name: str,
    ) -> list[CorrelatedAlert]:
        now = result.timestamp or time.time()
        self._prune(now)

        self._recent.append(
            {
                "sensor_id": result.sensor_id,
                "subsystem": subsystem,
                "protocol": protocol,
                "property_name": property_name,
                "value": result.value,
                "ts": now,
            }
        )

        if len(self._recent) < self.min_sources:
            return []

        distinct_sensors = {e["sensor_id"] for e in self._recent}
        if len(distinct_sensors) < self.min_sources:
            return []

        present_properties = {e["property_name"] for e in self._recent}
        pattern = _match_pattern(present_properties)

        if pattern is None:
            if len(distinct_sensors) < 3:
                return []
            hypothesis = (
                f"{len(distinct_sensors)} sensors from different sources anomalous simultaneously"
            )
            confidence = "low"
        else:
            hypothesis = pattern["hypothesis"]
            confidence = pattern["confidence"]

        key_parts = sorted(distinct_sensors)
        alert_id = f"{pattern['name'] if pattern else 'multi'}:{'|'.join(key_parts)}"
        if alert_id in self._emitted_ids:
            return []

        self._emitted_ids.add(alert_id)

        alert = CorrelatedAlert(
            alert_id=alert_id,
            triggered_at=now,
            sources=[
                {
                    "sensor_id": e["sensor_id"],
                    "subsystem": e["subsystem"],
                    "protocol": e["protocol"],
                    "value": e["value"],
                }
                for e in self._recent
                if e["sensor_id"] in distinct_sensors
            ],
            hypothesis=hypothesis,
            confidence=confidence,
            subsystems_involved=sorted({e["subsystem"] for e in self._recent}),
            protocols_involved=sorted({e["protocol"] for e in self._recent}),
        )

        logger.warning(
            "Correlated alert [%s]: %s (protocols: %s)",
            alert.alert_id,
            alert.hypothesis,
            alert.protocols_involved,
        )

        return [alert]

    def clear_alert(self, alert_id: str) -> None:
        self._emitted_ids.discard(alert_id)

    def pending_anomalies(self) -> list[dict]:
        now = time.time()
        self._prune(now)
        return list(self._recent)
