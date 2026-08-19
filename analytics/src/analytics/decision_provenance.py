from __future__ import annotations

import hashlib
import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class EvidenceLink:
    device_id: str
    subsystem: str
    protocol: str
    property_name: str
    value: float
    threshold: float
    observed_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "subsystem": self.subsystem,
            "protocol": self.protocol,
            "property_name": self.property_name,
            "value": self.value,
            "threshold": self.threshold,
            "observed_at": self.observed_at,
        }

    def sentence(self) -> str:
        return (
            f"{self.subsystem}/{self.property_name}={self.value:.1f} "
            f"(threshold {self.threshold:.1f}, via {self.protocol.upper()})"
        )


@dataclass
class DecisionRecord:
    decision_id: str
    command_id: Optional[str]
    policy_name: str
    label_zh: str
    hazard_rule: str
    target_device: str
    action: str
    params: dict
    severity: str
    confidence: str
    ontology_version: str
    decided_at: str
    evidence: list[EvidenceLink] = field(default_factory=list)
    outcome: str = "pending"
    audit_seq: Optional[int] = None
    audit_hash: Optional[str] = None

    @property
    def subsystems(self) -> list[str]:
        return sorted({e.subsystem for e in self.evidence})

    @property
    def protocols(self) -> list[str]:
        return sorted({e.protocol for e in self.evidence})

    def causal_chain(self) -> list[str]:
        return [e.sentence() for e in sorted(self.evidence, key=lambda x: x.observed_at)]

    def explanation_zh(self) -> str:
        parts = " 且 ".join(
            f"{e.subsystem} 的 {e.property_name} 为 {e.value:.1f}（阈值 {e.threshold:.1f}，经 {e.protocol.upper()} 采集）"
            for e in self.evidence
        )
        protos = " + ".join(p.upper() for p in self.protocols)
        return (
            f"因为 {parts}，规则 {self.hazard_rule} 判定为{self.label_zh}，"
            f"所以对 {self.target_device} 执行 {self.action}。"
            f"证据来自 {len(self.subsystems)} 个子系统、{protos} 协议，由语义层统一关联。"
        )

    def fingerprint(self) -> str:
        payload = {
            "decision_id": self.decision_id,
            "policy_name": self.policy_name,
            "hazard_rule": self.hazard_rule,
            "target_device": self.target_device,
            "action": self.action,
            "params": self.params,
            "ontology_version": self.ontology_version,
            "decided_at": self.decided_at,
            "evidence": [e.to_dict() for e in self.evidence],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "command_id": self.command_id,
            "policy_name": self.policy_name,
            "label_zh": self.label_zh,
            "hazard_rule": self.hazard_rule,
            "target_device": self.target_device,
            "action": self.action,
            "params": self.params,
            "severity": self.severity,
            "confidence": self.confidence,
            "ontology_version": self.ontology_version,
            "decided_at": self.decided_at,
            "outcome": self.outcome,
            "subsystems": self.subsystems,
            "protocols": self.protocols,
            "causal_chain": self.causal_chain(),
            "explanation_zh": self.explanation_zh(),
            "evidence": [e.to_dict() for e in self.evidence],
            "fingerprint": self.fingerprint(),
            "audit_seq": self.audit_seq,
            "audit_hash": self.audit_hash,
        }


def evidence_from_hazard(hazard: dict) -> list[EvidenceLink]:
    links = []
    for item in hazard.get("evidence", []):
        try:
            links.append(
                EvidenceLink(
                    device_id=str(item.get("device_id", "")),
                    subsystem=str(item.get("subsystem", "")),
                    protocol=str(item.get("protocol", "")),
                    property_name=str(item.get("property_name", "")),
                    value=float(item.get("value", 0.0)),
                    threshold=float(item.get("threshold", 0.0)),
                    observed_at=float(item.get("observed_at", 0.0)),
                )
            )
        except (TypeError, ValueError):
            continue
    return links


class DecisionLedger:
    def __init__(self, max_records: int = 500) -> None:
        self._lock = threading.RLock()
        self._records: list[DecisionRecord] = []
        self._by_id: dict[str, DecisionRecord] = {}
        self._max = max_records

    def reset(self) -> None:
        with self._lock:
            self._records.clear()
            self._by_id.clear()

    def record(
        self,
        policy_name: str,
        label_zh: str,
        hazard: dict,
        target_device: str,
        action: str,
        params: dict,
        severity: str,
        ontology_version: str,
        command_id: Optional[str] = None,
    ) -> DecisionRecord:
        record = DecisionRecord(
            decision_id=str(uuid.uuid4()),
            command_id=command_id,
            policy_name=policy_name,
            label_zh=label_zh,
            hazard_rule=str(hazard.get("rule_name", "")),
            target_device=target_device,
            action=action,
            params=dict(params),
            severity=severity,
            confidence=str(hazard.get("confidence", "unknown")),
            ontology_version=ontology_version,
            decided_at=datetime.now(timezone.utc).isoformat(),
            evidence=evidence_from_hazard(hazard),
        )
        with self._lock:
            self._records.insert(0, record)
            self._by_id[record.decision_id] = record
            for stale in self._records[self._max :]:
                self._by_id.pop(stale.decision_id, None)
            del self._records[self._max :]
        logger.info(
            "decision %s policy=%s rule=%s -> %s %s",
            record.decision_id[:8],
            policy_name,
            record.hazard_rule,
            target_device,
            action,
        )
        return record

    def attach_audit(self, decision_id: str, seq: int, entry_hash: str) -> None:
        with self._lock:
            record = self._by_id.get(decision_id)
            if record is not None:
                record.audit_seq = seq
                record.audit_hash = entry_hash

    def set_outcome(self, decision_id: str, outcome: str) -> None:
        with self._lock:
            record = self._by_id.get(decision_id)
            if record is not None:
                record.outcome = outcome

    def get(self, decision_id: str) -> Optional[DecisionRecord]:
        with self._lock:
            return self._by_id.get(decision_id)

    def by_command(self, command_id: str) -> Optional[DecisionRecord]:
        with self._lock:
            for record in self._records:
                if record.command_id == command_id:
                    return record
        return None

    def list(
        self,
        policy_name: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> list[DecisionRecord]:
        with self._lock:
            items = list(self._records)
        if policy_name:
            items = [r for r in items if r.policy_name == policy_name]
        if severity:
            items = [r for r in items if r.severity == severity]
        return items[:limit]

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)


ledger = DecisionLedger()
