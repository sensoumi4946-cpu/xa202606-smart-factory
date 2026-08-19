from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import z3

logger = logging.getLogger(__name__)

OPPOSING_ACTIONS = [
    frozenset({"open", "close"}),
    frozenset({"on", "off"}),
    frozenset({"start", "stop"}),
    frozenset({"engage", "release"}),
    frozenset({"raise", "lower"}),
]

SENSOR_DOMAINS = {
    "temperature": (-40.0, 120.0),
    "humidity": (0.0, 100.0),
    "co": (0.0, 1000.0),
    "smoke": (0.0, 1000.0),
    "combustible_gas": (0.0, 1000.0),
    "distance": (0.0, 450.0),
    "count": (0.0, 1000000.0),
    "occupancy": (0.0, 1.0),
    "light_state": (0.0, 1.0),
    "vibration": (0.0, 50.0),
    "pressure": (0.0, 1000.0),
}


@dataclass
class RuleCondition:
    property_name: str
    threshold: float
    direction: str


@dataclass
class VerifiedPolicy:
    name: str
    label_zh: str
    target_device: str
    engage_action: str
    release_action: str
    conditions: list[RuleCondition]
    hazard_rules: tuple[str, ...] = ()


@dataclass
class Conflict:
    kind: str
    policy_a: str
    policy_b: str
    target_device: str
    action_a: str
    action_b: str
    witness: dict[str, float]
    explanation_zh: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "policy_a": self.policy_a,
            "policy_b": self.policy_b,
            "target_device": self.target_device,
            "action_a": self.action_a,
            "action_b": self.action_b,
            "witness": self.witness,
            "explanation_zh": self.explanation_zh,
        }


@dataclass
class Certificate:
    verified: bool
    policy_count: int
    pair_count: int
    checks_run: int
    conflicts: list[Conflict] = field(default_factory=list)
    unreachable_policies: list[str] = field(default_factory=list)
    solver_version: str = ""
    generated_at: str = ""
    fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "policy_count": self.policy_count,
            "pair_count": self.pair_count,
            "checks_run": self.checks_run,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "unreachable_policies": self.unreachable_policies,
            "solver_version": self.solver_version,
            "generated_at": self.generated_at,
            "fingerprint": self.fingerprint,
        }

    def summary_zh(self) -> str:
        if self.verified:
            return (
                f"已对 {self.policy_count} 条安全策略、{self.pair_count} 组策略对"
                f"进行形式化验证，共 {self.checks_run} 次求解，"
                f"证明不存在任何传感器取值会导致同一设备收到互相冲突的指令。"
            )
        return (
            f"验证未通过：在 {self.policy_count} 条策略中发现 "
            f"{len(self.conflicts)} 处冲突，需修改后重新验证。"
        )


def _actions_oppose(a: str, b: str) -> bool:
    if a == b:
        return False
    pair = frozenset({a.lower(), b.lower()})
    return pair in OPPOSING_ACTIONS


def _domain_constraints(
    solver: z3.Solver, variables: dict[str, z3.ArithRef]
) -> None:
    for name, var in variables.items():
        low, high = SENSOR_DOMAINS.get(name, (-1e6, 1e6))
        solver.add(var >= low, var <= high)


def _condition_expr(
    condition: RuleCondition, variables: dict[str, z3.ArithRef]
) -> z3.BoolRef:
    var = variables[condition.property_name]
    if condition.direction == "above":
        return var > condition.threshold
    return var < condition.threshold


def _policy_expr(
    policy: VerifiedPolicy, variables: dict[str, z3.ArithRef]
) -> z3.BoolRef:
    if not policy.conditions:
        return z3.BoolVal(True)
    return z3.And(*[_condition_expr(c, variables) for c in policy.conditions])


def _collect_variables(policies: list[VerifiedPolicy]) -> dict[str, z3.ArithRef]:
    names = sorted(
        {c.property_name for p in policies for c in p.conditions}
    )
    return {name: z3.Real(name) for name in names}


def _witness(model: z3.ModelRef, variables: dict[str, z3.ArithRef]) -> dict[str, float]:
    out = {}
    for name, var in variables.items():
        value = model.eval(var, model_completion=True)
        try:
            out[name] = float(value.as_fraction())
        except AttributeError:
            out[name] = float(str(value))
    return out


def check_pair(
    a: VerifiedPolicy,
    b: VerifiedPolicy,
    variables: dict[str, z3.ArithRef],
) -> Optional[Conflict]:
    if a.target_device != b.target_device:
        return None
    if not _actions_oppose(a.engage_action, b.engage_action):
        return None

    solver = z3.Solver()
    _domain_constraints(solver, variables)
    solver.add(_policy_expr(a, variables))
    solver.add(_policy_expr(b, variables))

    if solver.check() != z3.sat:
        return None

    witness = _witness(solver.model(), variables)
    readable = "，".join(f"{k}={v:g}" for k, v in sorted(witness.items()))
    return Conflict(
        kind="opposing_actions",
        policy_a=a.name,
        policy_b=b.name,
        target_device=a.target_device,
        action_a=a.engage_action,
        action_b=b.engage_action,
        witness=witness,
        explanation_zh=(
            f"当 {readable} 时，策略 {a.name}（{a.label_zh}）要求对 "
            f"{a.target_device} 执行 {a.engage_action}，"
            f"而策略 {b.name}（{b.label_zh}）同时要求执行 {b.engage_action}，两者冲突。"
        ),
    )


def check_reachable(
    policy: VerifiedPolicy, variables: dict[str, z3.ArithRef]
) -> bool:
    solver = z3.Solver()
    _domain_constraints(solver, variables)
    solver.add(_policy_expr(policy, variables))
    return solver.check() == z3.sat


def verify(policies: list[VerifiedPolicy]) -> Certificate:
    variables = _collect_variables(policies)
    conflicts: list[Conflict] = []
    unreachable: list[str] = []
    checks = 0

    for policy in policies:
        checks += 1
        if policy.conditions and not check_reachable(policy, variables):
            unreachable.append(policy.name)

    pairs = 0
    for i, a in enumerate(policies):
        for b in policies[i + 1 :]:
            pairs += 1
            checks += 1
            conflict = check_pair(a, b, variables)
            if conflict is not None:
                conflicts.append(conflict)

    payload = {
        "policies": [
            {
                "name": p.name,
                "target": p.target_device,
                "engage": p.engage_action,
                "release": p.release_action,
                "conditions": [
                    [c.property_name, c.threshold, c.direction] for c in p.conditions
                ],
            }
            for p in sorted(policies, key=lambda x: x.name)
        ],
        "conflicts": [c.to_dict() for c in conflicts],
        "unreachable": sorted(unreachable),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(canonical.encode()).hexdigest()

    certificate = Certificate(
        verified=not conflicts,
        policy_count=len(policies),
        pair_count=pairs,
        checks_run=checks,
        conflicts=conflicts,
        unreachable_policies=sorted(unreachable),
        solver_version=z3.get_version_string(),
        generated_at=datetime.now(timezone.utc).isoformat(),
        fingerprint=fingerprint,
    )

    if certificate.verified:
        logger.info(
            "policy verification passed: %d policies, %d pairs, %d solver calls",
            len(policies),
            pairs,
            checks,
        )
    else:
        logger.error(
            "policy verification FAILED: %d conflicts", len(certificate.conflicts)
        )
    return certificate


def _conditions_from_hazard_rules(
    hazard_rules: tuple[str, ...], rule_table: dict[str, dict]
) -> list[RuleCondition]:
    conditions: list[RuleCondition] = []
    for rule_name in hazard_rules:
        rule = rule_table.get(rule_name)
        if not rule:
            continue
        for prop, (threshold, direction) in rule.get("conditions", {}).items():
            conditions.append(RuleCondition(prop, float(threshold), direction))
    return conditions


def from_safety_controller(controller, reasoner=None) -> list[VerifiedPolicy]:
    from analytics.hazard_reasoner import HAZARD_RULES

    rules = reasoner.rules if reasoner is not None else HAZARD_RULES
    rule_table = {r["name"]: r for r in rules}

    verified = []
    for policy in controller.policies:
        conditions = _conditions_from_hazard_rules(policy.hazard_rules, rule_table)
        verified.append(
            VerifiedPolicy(
                name=policy.name,
                label_zh=policy.label_zh,
                target_device=policy.target_device,
                engage_action=policy.engage_action,
                release_action=policy.release_action,
                conditions=conditions,
                hazard_rules=tuple(policy.hazard_rules),
            )
        )
    return verified


def verify_controller(controller, reasoner=None) -> Certificate:
    return verify(from_safety_controller(controller, reasoner))
