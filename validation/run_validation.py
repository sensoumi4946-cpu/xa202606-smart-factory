from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from semantic_layer.protocol_binding import (
    BindingRegistry,
    generate_all,
    validate_bindings,
)

CASES_DIR = Path(__file__).resolve().parent / "cases"

OK = "\033[92m"
BAD = "\033[91m"
DIM = "\033[90m"
OFF = "\033[0m"


@dataclass
class Case:
    cid: str
    name: str
    filename: str
    should_load: bool
    expect: list[str] = field(default_factory=list)


CASES = [
    Case("C1", "合法地址", "case1_valid_address.ttl", True),
    Case("C2", "非法地址", "case2_illegal_address.ttl", False,
         ["registerAddress", "functionCode"]),
    Case("C3", "类型不一致", "case3_type_mismatch.ttl", False,
         ["registerType", "scaleFactor", "pollIntervalMs"]),
]


@dataclass
class Result:
    case: Case
    ok: bool
    loaded: bool
    violations: list[str]
    ms: float
    note: str = ""


def run(case: Case) -> Result:
    turtle = (CASES_DIR / case.filename).read_text(encoding="utf-8")

    t0 = time.perf_counter()
    accepted, violations, _ = validate_bindings(turtle)
    ms = (time.perf_counter() - t0) * 1000.0

    if accepted != case.should_load:
        return Result(case, False, accepted, violations, ms, "预期与实际不符")

    blob = " ".join(violations)
    missing = [p for p in case.expect if p not in blob]
    if missing:
        return Result(case, False, accepted, violations, ms, f"缺少约束 {missing}")

    if not accepted:
        return Result(case, True, accepted, violations, ms,
                      f"拦截 {len(violations)} 项")

    registry = BindingRegistry()
    registry.load_turtle(turtle)
    adapters = generate_all(registry)
    lines = sum(len(s.splitlines()) for s in adapters.values())
    return Result(case, True, accepted, violations, ms,
                  f"生成 {'/'.join(sorted(adapters))} 共 {lines} 行")


def main() -> int:
    results = [run(c) for c in CASES]

    print()
    print("本体绑定约束验证")
    print()
    print(f"{'':2}{'用例':<5}{'名称':<12}{'预期':<6}{'实际':<6}{'耗时':>9}   {'结果':<6}说明")
    print(f"{'':2}{'-' * 74}")

    for r in results:
        want = "接受" if r.case.should_load else "拒绝"
        got = "接受" if r.loaded else "拒绝"
        mark = f"{OK}通过{OFF}" if r.ok else f"{BAD}失败{OFF}"
        print(f"{'':2}{r.case.cid:<5}{r.case.name:<12}{want:<6}{got:<6}"
              f"{r.ms:>7.1f}ms   {mark}  {r.note}")
        for v in r.violations:
            print(f"{'':2}{'':23}{DIM}{v}{OFF}")

    passed = sum(1 for r in results if r.ok)
    total = len(results)
    slowest = max(r.ms for r in results)

    print(f"{'':2}{'-' * 74}")
    print(f"{'':2}{passed}/{total} 通过    最慢 {slowest:.1f}ms    "
          f"拦截发生在加载阶段，未进入运行时")
    print()
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())