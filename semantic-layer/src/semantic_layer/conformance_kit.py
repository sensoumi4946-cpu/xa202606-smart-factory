from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from semantic_layer.meta_model import PropertyDefinition

logger = logging.getLogger(__name__)

SEVERITY_BLOCKING = "blocking"
SEVERITY_ADVISORY = "advisory"


@dataclass
class ConformanceCase:
    case_id: str
    title_zh: str
    property_name: str
    payload: dict[str, Any]
    expect_accept: bool
    severity: str
    rationale_zh: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "title_zh": self.title_zh,
            "property_name": self.property_name,
            "payload": self.payload,
            "expect_accept": self.expect_accept,
            "severity": self.severity,
            "rationale_zh": self.rationale_zh,
        }


@dataclass
class CaseOutcome:
    case: ConformanceCase
    accepted: bool
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.case.to_dict(),
            "accepted": self.accepted,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass
class ConformanceCertificate:
    device_id: str
    ontology_version: str
    generated_at: str
    total: int
    passed: int
    failed: int
    blocking_failures: int
    conformant: bool
    outcomes: list[CaseOutcome] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "ontology_version": self.ontology_version,
            "generated_at": self.generated_at,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "blocking_failures": self.blocking_failures,
            "conformant": self.conformant,
            "outcomes": [o.to_dict() for o in self.outcomes],
        }

    def summary_zh(self) -> str:
        if self.conformant:
            return (
                f"设备 {self.device_id} 通过一致性测试："
                f"{self.passed}/{self.total} 项通过，无阻断性问题，"
                f"本体版本 {self.ontology_version}。"
            )
        return (
            f"设备 {self.device_id} 未通过一致性测试："
            f"{self.failed} 项失败，其中 {self.blocking_failures} 项为阻断性问题。"
        )


UNIT_BY_PROPERTY = {
    "temperature": "celsius",
    "humidity": "percent",
    "co": "ppm",
    "smoke": "ppm",
    "combustible_gas": "ppm",
    "distance": "cm",
    "count": "count",
    "occupancy": "boolean",
    "light_state": "boolean",
    "vibration": "mm_per_sec",
    "pressure": "kpa",
}

WRONG_UNIT = {
    "celsius": "fahrenheit",
    "percent": "ratio",
    "ppm": "mg_per_m3",
    "cm": "metre",
    "count": "percent",
    "boolean": "celsius",
}


def _payload(
    device_id: str,
    subsystem: str,
    protocol: str,
    property_name: str,
    value: Any,
    unit: str,
) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "device_id": device_id,
        "subsystem": subsystem,
        "protocol": protocol,
        "measurements": [{"type": property_name, "value": value, "unit": unit}],
    }


def generate_cases(
    device_id: str,
    subsystem: str,
    protocol: str,
    properties: dict[str, PropertyDefinition],
) -> list[ConformanceCase]:
    cases: list[ConformanceCase] = []

    for name, definition in sorted(properties.items()):
        unit = UNIT_BY_PROPERTY.get(name, "")
        low, high = definition.min_value, definition.max_value
        midpoint = (low + high) / 2.0

        cases.append(
            ConformanceCase(
                case_id=f"{name}.nominal",
                title_zh=f"{name} 正常量程内数值应被接受",
                property_name=name,
                payload=_payload(device_id, subsystem, protocol, name, midpoint, unit),
                expect_accept=True,
                severity=SEVERITY_BLOCKING,
                rationale_zh=f"量程 [{low}, {high}] 中点必须能正常上报",
            )
        )
        cases.append(
            ConformanceCase(
                case_id=f"{name}.lower_bound",
                title_zh=f"{name} 下限值应被接受",
                property_name=name,
                payload=_payload(device_id, subsystem, protocol, name, low, unit),
                expect_accept=True,
                severity=SEVERITY_BLOCKING,
                rationale_zh=f"下限 {low} 属于合法量程，不得被误拒",
            )
        )
        cases.append(
            ConformanceCase(
                case_id=f"{name}.upper_bound",
                title_zh=f"{name} 上限值应被接受",
                property_name=name,
                payload=_payload(device_id, subsystem, protocol, name, high, unit),
                expect_accept=True,
                severity=SEVERITY_BLOCKING,
                rationale_zh=f"上限 {high} 属于合法量程，不得被误拒",
            )
        )
        cases.append(
            ConformanceCase(
                case_id=f"{name}.above_range",
                title_zh=f"{name} 超上限应被拒绝",
                property_name=name,
                payload=_payload(
                    device_id, subsystem, protocol, name, high + abs(high) + 100.0, unit
                ),
                expect_accept=False,
                severity=SEVERITY_BLOCKING,
                rationale_zh="传感器断线常表现为极大值，平台必须挡下",
            )
        )
        cases.append(
            ConformanceCase(
                case_id=f"{name}.below_range",
                title_zh=f"{name} 超下限应被拒绝",
                property_name=name,
                payload=_payload(
                    device_id, subsystem, protocol, name, low - abs(low) - 100.0, unit
                ),
                expect_accept=False,
                severity=SEVERITY_BLOCKING,
                rationale_zh="负向野值同样是典型故障特征",
            )
        )
        wrong = WRONG_UNIT.get(unit, "unknown_unit")
        cases.append(
            ConformanceCase(
                case_id=f"{name}.wrong_unit",
                title_zh=f"{name} 单位错误应被拒绝",
                property_name=name,
                payload=_payload(
                    device_id, subsystem, protocol, name, midpoint, wrong
                ),
                expect_accept=False,
                severity=SEVERITY_BLOCKING,
                rationale_zh=f"单位必须是 {unit}，混用单位是集成阶段最常见的错误",
            )
        )

    cases.append(
        ConformanceCase(
            case_id="schema.missing_version",
            title_zh="缺少 schema_version 应被拒绝",
            property_name="",
            payload={
                "device_id": device_id,
                "subsystem": subsystem,
                "protocol": protocol,
                "measurements": [],
            },
            expect_accept=False,
            severity=SEVERITY_BLOCKING,
            rationale_zh="报文必须自描述版本，否则无法演进",
        )
    )
    cases.append(
        ConformanceCase(
            case_id="schema.unknown_property",
            title_zh="未在本体中声明的属性应被拒绝",
            property_name="",
            payload=_payload(
                device_id, subsystem, protocol, "undeclared_property", 1.0, "ppm"
            ),
            expect_accept=False,
            severity=SEVERITY_BLOCKING,
            rationale_zh="平台只接受本体已声明的属性",
        )
    )
    cases.append(
        ConformanceCase(
            case_id="schema.empty_measurements",
            title_zh="空测量数组应被拒绝",
            property_name="",
            payload={
                "schema_version": "v1",
                "device_id": device_id,
                "subsystem": subsystem,
                "protocol": protocol,
                "measurements": [],
            },
            expect_accept=False,
            severity=SEVERITY_ADVISORY,
            rationale_zh="空报文浪费带宽，建议设备侧抑制",
        )
    )
    return cases


def default_validator(payload: dict[str, Any]) -> tuple[bool, str]:
    from semantic_layer.observation_gate import check_and_prepare
    from smart_factory_contracts.messages import UnifiedMessage

    try:
        message = UnifiedMessage(**payload)
    except Exception as exc:
        return False, f"contract rejected: {type(exc).__name__}"

    try:
        result = check_and_prepare(message)
    except Exception as exc:
        return False, f"gate error: {exc}"

    detail = "; ".join(str(v) for v in result.report.violations[:2])
    return result.accepted, detail


def run_kit(
    device_id: str,
    subsystem: str,
    protocol: str,
    properties: dict[str, PropertyDefinition],
    ontology_version: str,
    validator: Optional[Callable[[dict[str, Any]], tuple[bool, str]]] = None,
) -> ConformanceCertificate:
    check = validator or default_validator
    cases = generate_cases(device_id, subsystem, protocol, properties)

    outcomes: list[CaseOutcome] = []
    for case in cases:
        accepted, detail = check(case.payload)
        passed = accepted == case.expect_accept
        outcomes.append(
            CaseOutcome(case=case, accepted=accepted, passed=passed, detail=detail)
        )

    failed = [o for o in outcomes if not o.passed]
    blocking = [o for o in failed if o.case.severity == SEVERITY_BLOCKING]

    certificate = ConformanceCertificate(
        device_id=device_id,
        ontology_version=ontology_version,
        generated_at=datetime.now(timezone.utc).isoformat(),
        total=len(outcomes),
        passed=len(outcomes) - len(failed),
        failed=len(failed),
        blocking_failures=len(blocking),
        conformant=not blocking,
        outcomes=outcomes,
    )

    logger.info(
        "conformance kit for %s: %d/%d passed, %d blocking",
        device_id,
        certificate.passed,
        certificate.total,
        certificate.blocking_failures,
    )
    return certificate


def render(certificate: ConformanceCertificate) -> str:
    lines = [
        "",
        f"设备一致性测试  {certificate.device_id}",
        "-" * 66,
        f"  本体版本 {certificate.ontology_version}",
        f"  用例 {certificate.total}   通过 {certificate.passed}   "
        f"失败 {certificate.failed}   阻断 {certificate.blocking_failures}",
        "-" * 66,
    ]
    for outcome in certificate.outcomes:
        mark = "PASS" if outcome.passed else "FAIL"
        lines.append(f"  [{mark}] {outcome.case.case_id:<28} {outcome.case.title_zh}")
        if not outcome.passed and outcome.detail:
            lines.append(f"         {outcome.detail[:70]}")
    lines += ["-" * 66, f"  {certificate.summary_zh()}", ""]
    return "\n".join(lines)


def to_json(certificate: ConformanceCertificate) -> str:
    return json.dumps(certificate.to_dict(), ensure_ascii=False, indent=2)
