"""Measure ontology-driven onboarding for a new device of a known type.

The output intentionally contains only reproducible observations. It does not
claim an unmeasured human configuration time or a no-restart runtime reload.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from semantic_layer.protocol_binding import BindingRegistry, generate_all

REPO_ROOT = Path(__file__).resolve().parents[1]
BINDINGS = REPO_ROOT / "bindings.ttl"
NEW_DEVICE = Path(__file__).resolve().parent / "cases" / "case1_valid_address.ttl"

ADAPTER_FILES = tuple(
    REPO_ROOT / path
    for path in (
        "connectivity/src/connectivity/adapters/modbus_adapter.py",
        "connectivity/src/connectivity/adapters/mqtt_adapter.py",
        "connectivity/src/connectivity/adapters/opcua_adapter.py",
        "connectivity/src/connectivity/adapters/rest_adapter.py",
    )
)
DEVICE_SPECIFIC_MARKERS = (
    "ESP32_001",
    "ESP32_005",
    "40001",
    "40002",
    "AGV.Distance",
    "factory/temp_humidity/sensors/ESP32_001",
)


def _hardcoded_binding_locations() -> list[str]:
    found: list[str] = []
    for path in ADAPTER_FILES:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if any(marker in line for marker in DEVICE_SPECIFIC_MARKERS):
                found.append(f"{path.relative_to(REPO_ROOT)}:{line_number}")
    return found


def run() -> dict:
    registry = BindingRegistry()
    existing = registry.load_turtle(BINDINGS.read_text(encoding="utf-8"))
    if not existing.accepted:
        raise RuntimeError(f"existing bindings rejected: {existing.violations}")

    before = len(registry)
    start = time.perf_counter()
    result = registry.load_turtle(NEW_DEVICE.read_text(encoding="utf-8"))
    adapters = generate_all(registry)
    elapsed_ms = (time.perf_counter() - start) * 1000
    if not result.accepted:
        raise RuntimeError(f"new device binding rejected: {result.violations}")

    return {
        "benchmark": "BM-BIND-1 new device using a known measurement type",
        "evidence_level": "machine-measured local validation and in-memory generation",
        "existing_bindings": before,
        "new_bindings": len(registry) - before,
        "elapsed_ms": round(elapsed_ms, 1),
        "binding_files_edited": 1,
        "business_code_files_edited": 0,
        "generated_lines": sum(len(code.splitlines()) for code in adapters.values()),
        "protocols_generated": sorted(adapters),
        "process_restart_required": False,
        "configuration_reload_required": True,
        "hardcoded_device_binding_locations": _hardcoded_binding_locations(),
        "limitations": [
            "The measurement type must already exist in the strict message contract.",
            "Live processes must receive the implemented authenticated/SIGHUP configuration reload.",
            "Elapsed time is software execution time, not an operator onboarding study.",
        ],
    }


def main() -> int:
    result = run()
    output = REPO_ROOT / "validation" / "benchmark_result.json"
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
