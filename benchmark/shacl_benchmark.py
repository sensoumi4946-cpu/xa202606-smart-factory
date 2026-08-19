from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from semantic_layer.observation_gate import check_and_prepare
from smart_factory_contracts.messages import (
    Measurement,
    MeasurementType,
    Protocol,
    Subsystem,
    UnifiedMessage,
    Unit,
)

WARMUP = 20


@dataclass
class StageResult:
    stage: str
    samples: int
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    throughput_per_s: float


def _message(index: int) -> UnifiedMessage:
    return UnifiedMessage(
        schema_version="v1",
        device_id=f"ESP32_{index % 5:03d}_bench",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        measurements=[
            Measurement(
                type=MeasurementType.TEMPERATURE,
                value=20.0 + (index % 200) * 0.1,
                unit=Unit.CELSIUS,
            ),
            Measurement(
                type=MeasurementType.HUMIDITY,
                value=40.0 + (index % 400) * 0.1,
                unit=Unit.PERCENT,
            ),
        ],
    )


def _summarise(stage: str, timings: list[float]) -> StageResult:
    ordered = sorted(timings)
    n = len(ordered)

    def pct(q: float) -> float:
        return ordered[min(n - 1, int(q * n))]

    mean = statistics.fmean(ordered)
    return StageResult(
        stage=stage,
        samples=n,
        mean_ms=round(mean, 3),
        p50_ms=round(pct(0.50), 3),
        p95_ms=round(pct(0.95), 3),
        p99_ms=round(pct(0.99), 3),
        max_ms=round(ordered[-1], 3),
        throughput_per_s=round(1000.0 / mean, 1) if mean > 0 else 0.0,
    )


def measure_validation(iterations: int) -> StageResult:
    for i in range(WARMUP):
        check_and_prepare(_message(i))

    timings = []
    for i in range(iterations):
        msg = _message(i)
        start = time.perf_counter()
        check_and_prepare(msg)
        timings.append((time.perf_counter() - start) * 1000.0)
    return _summarise("shacl_validation", timings)


def measure_parse_only(iterations: int) -> StageResult:
    payload = _message(0).model_dump(mode="json")
    for _ in range(WARMUP):
        UnifiedMessage(**payload)

    timings = []
    for _ in range(iterations):
        start = time.perf_counter()
        UnifiedMessage(**payload)
        timings.append((time.perf_counter() - start) * 1000.0)
    return _summarise("contract_parse", timings)


def run(iterations: int = 500) -> dict[str, Any]:
    parse = measure_parse_only(iterations)
    validate = measure_validation(iterations)

    ceiling = validate.throughput_per_s
    return {
        "benchmark": "BM-SHACL-1 ingest path validation cost",
        "iterations": iterations,
        "stages": [asdict(parse), asdict(validate)],
        "single_worker_ceiling_msg_per_s": round(ceiling, 1),
        "devices_at_2hz": int(ceiling / 2),
        "devices_at_0_5hz": int(ceiling / 0.5),
        "notes": [
            "SHACL validation runs synchronously in the ingest request path.",
            "The figure above is the measured ceiling for one uvicorn worker."
        ],
    }


def render(result: dict[str, Any]) -> str:
    lines = [
        "",
        "BM-SHACL-1  接入路径校验开销",
        "-" * 62,
        f"  {'阶段':<20}{'p50':>9}{'p95':>9}{'p99':>9}{'吞吐/s':>10}",
        "  " + "-" * 58,
    ]
    for stage in result["stages"]:
        lines.append(
            f"  {stage['stage']:<20}{stage['p50_ms']:>8.2f}ms"
            f"{stage['p95_ms']:>8.2f}ms{stage['p99_ms']:>8.2f}ms"
            f"{stage['throughput_per_s']:>10.1f}"
        )
    lines += [
        "  " + "-" * 58,
        f"  单 worker 吞吐上限   {result['single_worker_ceiling_msg_per_s']} 条/秒",
        f"  按 2 Hz 上报估算     可带 {result['devices_at_2hz']} 台设备",
        f"  按 0.5 Hz 上报估算   可带 {result['devices_at_0_5hz']} 台设备",
        "",
        "  校验目前在请求路径内同步执行。迁移路径：改为入队后返回 202，",
        "  校验仍然强制执行，但不再占用请求延迟。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="SHACL ingest cost benchmark")
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--json", type=str, default=None)
    args = parser.parse_args()

    result = run(args.iterations)
    print(render(result))
    if args.json:
        Path(args.json).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  写入 {args.json}\n")


if __name__ == "__main__":
    main()
