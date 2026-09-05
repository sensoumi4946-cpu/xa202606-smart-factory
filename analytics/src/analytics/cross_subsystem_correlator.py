from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from analytics.anomaly_detector import AnomalyResult, canonical_property

logger = logging.getLogger(__name__)

DEFAULT_CORRELATION_WINDOW = 10.0

DEFAULT_MIN_SOURCES = 2


@dataclass
class CorrelatedAlert:
    alert_id: str
    triggered_at: float
    sources: list[dict]        
    hypothesis: str            
    confidence: str            
    subsystems_involved: list[str]
    protocols_involved: list[str]

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "triggered_at": self.triggered_at,
            "sources": self.sources,
            "hypothesis": self.hypothesis,
            "confidence": self.confidence,
            "subsystems_involved": self.subsystems_involved,
            "protocols_involved": self.protocols_involved,
        }


_PATTERNS: list[dict] = [
    {
        "name": "fire_risk",
        "required_properties": {"co", "temperature"},
        "hypothesis": "Simultaneous rise in CO and temperature — possible fire or combustion event",
        "confidence": "high",
    },
    {
        "name": "smouldering",
        "required_properties": {"smoke", "co"},
        "hypothesis": "Smoke and CO rising together — possible smouldering material before open flame",
        "confidence": "high",
    },
    {
        "name": "gas_accumulation",
        "required_properties": {"combustible_gas", "temperature"},
        "hypothesis": "Combustible gas anomaly with temperature change — possible leak near a heat source",
        "confidence": "high",
    },
    {
        "name": "unattended_hazard",
        "required_properties": {"combustible_gas", "occupancy"},
        "hypothesis": "Gas anomaly in an area with no personnel — leak may go unnoticed",
        "confidence": "medium",
    },
    {
        "name": "environment_stress",
        "required_properties": {"temperature", "humidity"},
        "hypothesis": "Temperature and humidity anomalies together — condensation or HVAC failure risk",
        "confidence": "medium",
    },
]


def _match_pattern(property_names: set[str]) -> Optional[dict]:
    for pattern in _PATTERNS:
        if pattern["required_properties"].issubset(property_names):
            return pattern
    return None


class CrossSubsystemCorrelator:
    pass





    def __init__(
        self,
        window_seconds: float = DEFAULT_CORRELATION_WINDOW,
        min_sources: int = DEFAULT_MIN_SOURCES,
    ) -> None:
        self.window_seconds = window_seconds
        self.min_sources = min_sources
        
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
                "property_name": canonical_property(property_name),
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