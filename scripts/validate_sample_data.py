"""Validate JSONL observations against contract, SHACL, and protocol bindings."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from semantic_layer.observation_gate import check_and_prepare
from semantic_layer.protocol_binding import BindingRegistry
from smart_factory_contracts.messages import UnifiedMessage

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = REPO_ROOT / "data" / "samples" / "five_subsystems.jsonl"
DEFAULT_BINDINGS = REPO_ROOT / "bindings.ttl"


@dataclass
class RecordResult:
    line: int
    device_id: str
    contract_valid: bool
    semantic_valid: bool
    binding_covered: bool
    errors: list[str]


def _binding_coverage(
    message: UnifiedMessage, registry: BindingRegistry
) -> tuple[bool, list[str]]:
    bindings = registry.for_device(message.device_id)
    declared = {
        (binding.protocol, binding.property_name, binding.canonical_subsystem)
        for binding in bindings
    }
    missing = [
        f"{message.protocol.value}:{measurement.type.value}:{message.subsystem.value}"
        for measurement in message.measurements
        if (
            message.protocol.value,
            measurement.type.value,
            message.subsystem.value,
        )
        not in declared
    ]
    return not missing, missing


def validate_file(data_path: Path, bindings_path: Path) -> list[RecordResult]:
    registry = BindingRegistry()
    loaded = registry.load_turtle(bindings_path.read_text(encoding="utf-8"))
    if not loaded.accepted:
        raise ValueError(f"bindings rejected: {loaded.violations}")

    results: list[RecordResult] = []
    for line_number, raw_line in enumerate(
        data_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not raw_line.strip():
            continue
        errors: list[str] = []
        try:
            payload = json.loads(raw_line)
            message = UnifiedMessage.model_validate(payload)
        except Exception as exc:
            results.append(
                RecordResult(line_number, "unknown", False, False, False, [str(exc)])
            )
            continue

        gate = check_and_prepare(message)
        if not gate.accepted:
            errors.extend(gate.report.violations)
        covered, missing = _binding_coverage(message, registry)
        errors.extend(f"missing binding {item}" for item in missing)
        results.append(
            RecordResult(
                line_number,
                message.device_id,
                True,
                gate.accepted,
                covered,
                errors,
            )
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path, nargs="?", default=DEFAULT_DATA)
    parser.add_argument("--bindings", type=Path, default=DEFAULT_BINDINGS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = validate_file(args.data, args.bindings)
    passed = all(
        item.contract_valid and item.semantic_valid and item.binding_covered
        for item in results
    )
    if args.json:
        print(json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2))
    else:
        for item in results:
            state = "PASS" if not item.errors else "FAIL"
            print(f"line={item.line} device={item.device_id} {state}")
            for error in item.errors:
                print(f"  - {error}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
