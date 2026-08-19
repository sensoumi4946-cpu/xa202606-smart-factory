from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_MIN_INTERVAL_S = 20.0
DEFAULT_CLEAR_HOLD_S = 30.0


@dataclass
class ControlAction:
    action_id: str
    policy_name: str
    label_zh: str
    device_id: str
    subsystem: str
    action: str
    params: dict
    trigger: str
    severity: str
    issued_at: float
    auto: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "policy_name": self.policy_name,
            "label_zh": self.label_zh,
            "device_id": self.device_id,
            "subsystem": self.subsystem,
            "action": self.action,
            "params": self.params,
            "trigger": self.trigger,
            "severity": self.severity,
            "issued_at": self.issued_at,
            "auto": self.auto,
        }


@dataclass
class Policy:
    name: str
    label_zh: str
    hazard_rules: tuple[str, ...]
    target_device: str
    target_subsystem: str
    engage_action: str
    release_action: str
    engage_params: dict = field(default_factory=dict)
    release_params: dict = field(default_factory=dict)
    severity: str = "critical"


DEFAULT_POLICIES: list[Policy] = [
    Policy(
        name="gas_isolation",
        label_zh="燃气紧急切断",
        hazard_rules=("gas_leak_unattended", "smouldering"),
        target_device="valve_gas_main",
        target_subsystem="gas",
        engage_action="close",
        release_action="open",
        engage_params={"mode": "emergency"},
        severity="critical",
    ),
    Policy(
        name="fire_ventilation",
        label_zh="火灾排风",
        hazard_rules=("fire_risk",),
        target_device="hvac_exhaust_01",
        target_subsystem="hvac",
        engage_action="on",
        release_action="off",
        engage_params={"speed": 100, "mode": "exhaust"},
        severity="critical",
    ),
    Policy(
        name="hvac_dehumidify",
        label_zh="除湿通风",
        hazard_rules=("condensation_risk",),
        target_device="hvac_exhaust_01",
        target_subsystem="hvac",
        engage_action="on",
        release_action="off",
        engage_params={"speed": 60, "mode": "dehumidify"},
        severity="warning",
    ),
]


class SafetyController:
    def __init__(
        self,
        policies: Optional[list[Policy]] = None,
        min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
        clear_hold_s: float = DEFAULT_CLEAR_HOLD_S,
        enabled: bool = True,
    ) -> None:
        self.policies = list(policies or DEFAULT_POLICIES)
        self.min_interval_s = min_interval_s
        self.clear_hold_s = clear_hold_s
        self.enabled = enabled
        self._engaged: dict[str, float] = {}
        self._last_action: dict[str, float] = {}
        self._history: list[ControlAction] = []
        self._manual_override: set[str] = set()

    def reset(self) -> None:
        self._engaged.clear()
        self._last_action.clear()
        self._history.clear()
        self._manual_override.clear()

    def is_engaged(self, policy_name: str) -> bool:
        return policy_name in self._engaged

    def engaged_policies(self) -> list[str]:
        return sorted(self._engaged)

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        return [a.to_dict() for a in self._history[:limit]]

    def set_manual_override(self, policy_name: str, active: bool) -> None:
        if active:
            self._manual_override.add(policy_name)
        else:
            self._manual_override.discard(policy_name)

    def _policies_for(self, rule_name: str) -> list[Policy]:
        return [p for p in self.policies if rule_name in p.hazard_rules]

    def on_hazards(
        self,
        hazards: list[dict],
        timestamp: Optional[float] = None,
    ) -> list[ControlAction]:
        if not self.enabled:
            return []

        now = time.time() if timestamp is None else float(timestamp)
        actions: list[ControlAction] = []
        seen_rules = {h.get("rule_name") for h in hazards}

        for rule_name in seen_rules:
            if not rule_name:
                continue
            for policy in self._policies_for(rule_name):
                if policy.name in self._manual_override:
                    continue
                if policy.name in self._engaged:
                    self._engaged[policy.name] = now
                    continue

                last = self._last_action.get(policy.name)
                if last is not None and now - last < self.min_interval_s:
                    continue

                action = ControlAction(
                    action_id=str(uuid.uuid4()),
                    policy_name=policy.name,
                    label_zh=policy.label_zh,
                    device_id=policy.target_device,
                    subsystem=policy.target_subsystem,
                    action=policy.engage_action,
                    params=dict(policy.engage_params),
                    trigger=rule_name,
                    severity=policy.severity,
                    issued_at=now,
                )
                self._engaged[policy.name] = now
                self._last_action[policy.name] = now
                self._history.insert(0, action)
                del self._history[200:]
                actions.append(action)
                logger.warning(
                    "Safety policy %s engaged by %s -> %s %s",
                    policy.name,
                    rule_name,
                    policy.target_device,
                    policy.engage_action,
                )

        return actions

    def tick(self, timestamp: Optional[float] = None) -> list[ControlAction]:
        if not self.enabled:
            return []

        now = time.time() if timestamp is None else float(timestamp)
        actions: list[ControlAction] = []

        for policy in self.policies:
            engaged_at = self._engaged.get(policy.name)
            if engaged_at is None:
                continue
            if now - engaged_at < self.clear_hold_s:
                continue
            if policy.name in self._manual_override:
                continue

            action = ControlAction(
                action_id=str(uuid.uuid4()),
                policy_name=policy.name,
                label_zh=policy.label_zh,
                device_id=policy.target_device,
                subsystem=policy.target_subsystem,
                action=policy.release_action,
                params=dict(policy.release_params),
                trigger="hazard_cleared",
                severity="info",
                issued_at=now,
            )
            del self._engaged[policy.name]
            self._last_action[policy.name] = now
            self._history.insert(0, action)
            del self._history[200:]
            actions.append(action)
            logger.info("Safety policy %s released", policy.name)

        return actions


async def execute_actions(
    actions: list[ControlAction],
    dispatch: Callable,
    record_command: Optional[Callable] = None,
    audit: Optional[Callable] = None,
) -> list[dict[str, Any]]:
    results = []
    for action in actions:
        command_id = (
            record_command(action.device_id, action.action, action.params)
            if record_command
            else action.action_id
        )
        ok = await dispatch(
            command_id=command_id,
            device_id=action.device_id,
            action=action.action,
            params=action.params,
            subsystem=action.subsystem,
        )
        if audit:
            audit(
                device_id=action.device_id,
                action=action.action,
                outcome="dispatched" if ok else "failed",
                actor=f"safety_controller:{action.policy_name}",
                command_id=command_id,
                params=action.params,
                detail=f"auto-engaged by {action.trigger}",
            )
        results.append(
            {**action.to_dict(), "command_id": command_id, "dispatched": ok}
        )
    return results
