from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from analytics.thresholds import resolver

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_S = 20.0
DEFAULT_COOLDOWN_S = 30.0


@dataclass
class Evidence:
    device_id: str
    subsystem: str
    protocol: str
    property_name: str
    value: float
    threshold: float
    observed_at: float


@dataclass
class HazardAlert:
    hazard_id: str
    rule_name: str
    label_zh: str
    label_en: str
    severity: str
    confidence: str
    triggered_at: float
    evidence: list[Evidence] = field(default_factory=list)
    recommended_action: str = ""

    @property
    def subsystems(self) -> list[str]:
        return sorted({e.subsystem for e in self.evidence})

    @property
    def protocols(self) -> list[str]:
        return sorted({e.protocol for e in self.evidence})

    def chain(self) -> list[str]:
        parts = []
        for e in sorted(self.evidence, key=lambda x: x.observed_at):
            parts.append(
                f"{e.subsystem}/{e.property_name}={e.value:.1f} "
                f"(>{e.threshold:.1f}, via {e.protocol.upper()})"
            )
        return parts

    def to_dict(self) -> dict:
        return {
            "hazard_id": self.hazard_id,
            "rule_name": self.rule_name,
            "label_zh": self.label_zh,
            "label_en": self.label_en,
            "severity": self.severity,
            "confidence": self.confidence,
            "triggered_at": self.triggered_at,
            "subsystems": self.subsystems,
            "protocols": self.protocols,
            "chain": self.chain(),
            "recommended_action": self.recommended_action,
            "evidence": [
                {
                    "device_id": e.device_id,
                    "subsystem": e.subsystem,
                    "protocol": e.protocol,
                    "property_name": e.property_name,
                    "value": e.value,
                    "threshold": e.threshold,
                    "observed_at": e.observed_at,
                }
                for e in self.evidence
            ],
        }


HAZARD_RULES: list[dict] = [
    {
        "name": "fire_risk",
        "label_zh": "火灾风险",
        "label_en": "Fire risk",
        "severity": "critical",
        "confidence": "high",
        "conditions": {
            "co": (35.0, "above"),
            "temperature": (38.0, "above"),
        },
        "action": "疏散人员，切断电源，启动排风",
    },
    {
        "name": "smouldering",
        "label_zh": "阴燃风险",
        "label_en": "Smouldering material",
        "severity": "critical",
        "confidence": "medium",
        "conditions": {
            "smoke": (8.0, "above"),
            "co": (25.0, "above"),
        },
        "action": "检查产线设备，准备灭火",
    },
    {
        "name": "gas_leak_unattended",
        "label_zh": "无人区域燃气泄漏",
        "label_en": "Gas leak in unoccupied area",
        "severity": "critical",
        "confidence": "high",
        "conditions": {
            "combustible_gas": (3.0, "above"),
            "occupancy": (0.5, "below"),
        },
        "action": "远程关闭气阀，禁止人员进入",
    },
    {
        "name": "agv_collision_risk",
        "label_zh": "AGV 碰撞风险",
        "label_en": "AGV collision risk",
        "severity": "warning",
        "confidence": "high",
        "conditions": {
            "distance": (30.0, "below"),
            "occupancy": (0.5, "above"),
        },
        "action": "AGV 减速停车，声光提示",
    },
    {
        "name": "condensation_risk",
        "label_zh": "高温高湿风险",
        "label_en": "Heat and humidity risk",
        "severity": "warning",
        "confidence": "medium",
        "conditions": {
            "temperature": (35.0, "above"),
            "humidity": (80.0, "above"),
        },
        "action": "开启除湿与通风，检查冷凝水",
    },
]


def _breached(value: float, threshold: float, direction: str) -> bool:
    return value > threshold if direction == "above" else value < threshold


class HazardReasoner:
    def __init__(
        self,
        rules: Optional[list[dict]] = None,
        window_s: float = DEFAULT_WINDOW_S,
        cooldown_s: float = DEFAULT_COOLDOWN_S,
        use_ontology_thresholds: bool = True,
    ) -> None:
        self.rules = list(rules or HAZARD_RULES)
        self.window_s = window_s
        self.cooldown_s = cooldown_s
        self.use_ontology_thresholds = use_ontology_thresholds
        self._facts: dict[str, Evidence] = {}
        self._last_fired: dict[str, float] = {}

    def reset(self) -> None:
        self._facts.clear()
        self._last_fired.clear()

    def _resolve(
        self, prop: str, declared: tuple[float, str]
    ) -> tuple[float, str]:
        if self.use_ontology_thresholds:
            resolved = resolver.threshold_for(prop)
            if resolved is not None:
                return float(resolved[0]), declared[1]
        return declared

    def _prune(self, now: float) -> None:
        stale = [k for k, e in self._facts.items() if now - e.observed_at > self.window_s]
        for k in stale:
            del self._facts[k]

    def observe(
        self,
        device_id: str,
        subsystem: str,
        protocol: str,
        measurements: list[dict],
        timestamp: Optional[float] = None,
    ) -> list[HazardAlert]:
        now = time.time() if timestamp is None else float(timestamp)
        self._prune(now)

        for m in measurements:
            prop = str(m.get("type") or m.get("property_name") or "").lower()
            value = m.get("value")
            if not prop or value is None:
                continue
            try:
                self._facts[prop] = Evidence(
                    device_id=device_id,
                    subsystem=subsystem,
                    protocol=str(protocol).lower(),
                    property_name=prop,
                    value=float(value),
                    threshold=0.0,
                    observed_at=now,
                )
            except (TypeError, ValueError):
                continue

        return self._evaluate(now)

    def _evaluate(self, now: float) -> list[HazardAlert]:
        fired: list[HazardAlert] = []

        for rule in self.rules:
            conditions = rule["conditions"]
            evidence: list[Evidence] = []
            satisfied = True

            for prop, declared in conditions.items():
                threshold, direction = self._resolve(prop, declared)
                fact = self._facts.get(prop)
                if fact is None or not _breached(fact.value, threshold, direction):
                    satisfied = False
                    break
                evidence.append(
                    Evidence(
                        device_id=fact.device_id,
                        subsystem=fact.subsystem,
                        protocol=fact.protocol,
                        property_name=fact.property_name,
                        value=fact.value,
                        threshold=threshold,
                        observed_at=fact.observed_at,
                    )
                )

            if not satisfied:
                continue

            span = max(e.observed_at for e in evidence) - min(
                e.observed_at for e in evidence
            )
            if span > self.window_s:
                continue

            last = self._last_fired.get(rule["name"])
            if last is not None and now - last < self.cooldown_s:
                continue
            self._last_fired[rule["name"]] = now

            alert = HazardAlert(
                hazard_id=str(uuid.uuid4()),
                rule_name=rule["name"],
                label_zh=rule["label_zh"],
                label_en=rule["label_en"],
                severity=rule["severity"],
                confidence=rule["confidence"],
                triggered_at=now,
                evidence=evidence,
                recommended_action=rule["action"],
            )
            logger.warning(
                "Hazard %s (%s) subsystems=%s protocols=%s",
                alert.rule_name,
                alert.label_en,
                alert.subsystems,
                alert.protocols,
            )
            fired.append(alert)

        return fired

    def clear(self, rule_name: str) -> None:
        self._last_fired.pop(rule_name, None)
