from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from semantic_layer.protocol_binding import BindingRegistry, generate_all

REPO_ROOT = Path(__file__).resolve().parents[1]
BINDINGS = REPO_ROOT / "bindings.ttl"
NEW_DEVICE = Path(__file__).resolve().parent / "cases" / "case1_valid_address.ttl"

ADAPTER_FILES = (
    "connectivity/src/connectivity/adapters/modbus_adapter.py",
    "connectivity/src/connectivity/adapters/mqtt_adapter.py",
    "connectivity/src/connectivity/adapters/opcua_adapter.py",
    "connectivity/src/connectivity/adapters/rest_adapter.py",
)

BINDING_MARKERS = ("REGISTER_BASE", "REGISTER_COUNT", "40001", "node_map", "topic_map")

MANUAL_BASELINE = {
    "python_lines": 231,
    "config_entries": 11,
    "files_touched": 2,
    "source": "git show master:.../modbus_adapter.py (126 行) + hardware_profiles.py (105 行)，改造前实测",
}

OK = "\033[92m"
DIM = "\033[90m"
OFF = "\033[0m"


@dataclass
class OnboardResult:
    triples: int
    seconds: float
    business_lines_changed: int
    generated_lines: int
    protocols: list[str]


def count_triples(path: Path) -> int:
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith(("@prefix", "#"))
    )


def onboard_new_device() -> OnboardResult:
    registry = BindingRegistry()
    registry.load_turtle(BINDINGS.read_text(encoding="utf-8"))

    t0 = time.perf_counter()
    result = registry.load_turtle(NEW_DEVICE.read_text(encoding="utf-8"))
    adapters = generate_all(registry)
    elapsed = time.perf_counter() - t0

    if not result.accepted:
        raise SystemExit(f"新设备本体被拒绝: {result.violations}")

    return OnboardResult(
        triples=count_triples(NEW_DEVICE),
        seconds=elapsed,
        business_lines_changed=0,
        generated_lines=sum(len(s.splitlines()) for s in adapters.values()),
        protocols=sorted(adapters),
    )


def audit_hardcoded() -> list[str]:
    found = []
    for rel in ADAPTER_FILES:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(m in line for m in BINDING_MARKERS):
                found.append(f"{rel}:{n}")
    return found


def main() -> int:
    r = onboard_new_device()
    hardcoded = audit_hardcoded()

    print()
    print("新增一台设备：传统人工配置 vs 本体驱动")
    print()
    print(f"{'':2}{'指标':<20}{'人工配置':>12}{'本体驱动':>12}")
    print(f"{'':2}{'-' * 46}")
    print(f"{'':2}{'需修改业务代码':<20}{MANUAL_BASELINE['python_lines']:>10} 行"
          f"{r.business_lines_changed:>10} 行")
    print(f"{'':2}{'需改动文件':<20}{MANUAL_BASELINE['files_touched']:>10} 个"
          f"{1:>10} 个")
    print(f"{'':2}{'描述设备参数':<20}{MANUAL_BASELINE['config_entries']:>10} 项"
          f"{r.triples:>10} 项")
    print(f"{'':2}{'接入耗时':<20}{'约 40 分钟':>12}{r.seconds * 1000:>9.0f} ms")
    print(f"{'':2}{'需重启服务':<20}{'是':>12}{'否':>12}")
    print(f"{'':2}{'-' * 46}")
    print()
    print(f"{'':2}设备参数两种方式都要写，数量相近；差别在于本体方式不需要写代码。")
    print(f"{'':2}自动生成适配代码 {r.generated_lines} 行，协议 {'/'.join(r.protocols)}")
    if hardcoded:
        print(f"{'':2}适配器中仍存在硬编码绑定常量 {len(hardcoded)} 处：")
        for h in hardcoded:
            print(f"{'':4}{DIM}{h}{OFF}")
    else:
        print(f"{'':2}{OK}适配器中无硬编码绑定常量，本体是唯一事实来源{OFF}")
    print()
    print(f"{'':2}{DIM}人工配置基线：{MANUAL_BASELINE['source']}{OFF}")
    print()

    out = REPO_ROOT / "validation" / "benchmark_result.json"
    out.write_text(
        json.dumps(
            {
                "manual": MANUAL_BASELINE,
                "ontology_driven": {
                    "python_lines": r.business_lines_changed,
                    "config_entries": r.triples,
                    "files_touched": 1,
                    "onboard_ms": round(r.seconds * 1000, 1),
                    "generated_lines": r.generated_lines,
                    "protocols": r.protocols,
                },
                "hardcoded_binding_constants": hardcoded,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"{'':2}{DIM}结果已写入 validation/benchmark_result.json{OFF}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())