from __future__ import annotations

import argparse
import asyncio
import csv
import gc
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

try:
    import psutil
except ImportError:
    psutil = None


def _make_message(protocol: str = "modbus", subsystem: str = "gas"):
    from smart_factory_contracts.messages import (
        Measurement,
        MeasurementType,
        Protocol,
        Subsystem,
        Unit,
        UnifiedMessage,
    )

    protocols = {
        "modbus": Protocol.MODBUS,
        "mqtt": Protocol.MQTT,
        "opcua": Protocol.OPCUA,
        "rest": Protocol.REST,
    }
    subsystems = {
        "gas": (Subsystem.GAS, MeasurementType.CO, 7.3, Unit.PPM),
        "temp_humidity": (
            Subsystem.TEMP_HUMIDITY,
            MeasurementType.TEMPERATURE,
            26.1,
            Unit.CELSIUS,
        ),
    }
    sub, mtype, value, unit = subsystems[subsystem]
    return UnifiedMessage(
        schema_version="v1",
        device_id="ESP32_BENCH",
        subsystem=sub,
        protocol=protocols[protocol],
        measurements=[Measurement(type=mtype, value=value, unit=unit)],
    )


@dataclass
class Latency:
    name: str
    samples: list[float] = field(default_factory=list)
    failures: int = 0

    @property
    def n(self) -> int:
        return len(self.samples)

    def pct(self, q: float) -> float:
        if not self.samples:
            return 0.0
        ordered = sorted(self.samples)
        idx = min(len(ordered) - 1, int(q * len(ordered)))
        return ordered[idx]

    @property
    def mean(self) -> float:
        return statistics.fmean(self.samples) if self.samples else 0.0

    @property
    def stdev(self) -> float:
        return statistics.stdev(self.samples) if len(self.samples) > 1 else 0.0

    def row(self) -> dict:
        return {
            "stage": self.name,
            "n": self.n,
            "mean_ms": round(self.mean, 3),
            "p50_ms": round(self.pct(0.50), 3),
            "p95_ms": round(self.pct(0.95), 3),
            "p99_ms": round(self.pct(0.99), 3),
            "max_ms": round(max(self.samples), 3) if self.samples else 0.0,
            "stdev_ms": round(self.stdev, 3),
            "failures": self.failures,
        }


def _measure(name: str, fn: Callable, runs: int) -> Latency:
    result = Latency(name)
    fn()
    for _ in range(runs):
        start = time.perf_counter()
        try:
            fn()
        except Exception:
            result.failures += 1
            continue
        result.samples.append((time.perf_counter() - start) * 1000.0)
    return result


def stage_rdf_mapping(runs: int) -> Latency:
    from semantic_layer.mapping import to_rdf_graph

    msg = _make_message()
    return _measure("RDF 映射", lambda: to_rdf_graph(msg), runs)


def stage_shacl_structural(runs: int) -> Latency:
    from semantic_layer.mapping import to_rdf_graph
    from semantic_layer.shacl_runner import validate

    graph = to_rdf_graph(_make_message())
    return _measure("SHACL 结构校验", lambda: validate(graph), runs)


def stage_shacl_domain(runs: int) -> Latency:
    from semantic_layer.mapping import to_rdf_graph
    from semantic_layer.shacl_runner import validate_with_domain

    graph = to_rdf_graph(_make_message())
    return _measure("SHACL 域校验", lambda: validate_with_domain(graph), runs)


def stage_unit_harmonizer(runs: int) -> Latency:
    from semantic_layer.mapping import to_rdf_graph
    from semantic_layer.semantic_unit_harmonizer import enrich_graph_with_qudt

    graph = to_rdf_graph(_make_message())
    return _measure("单位归一", lambda: enrich_graph_with_qudt(graph), runs)


def stage_full_gate(runs: int) -> Latency:
    from semantic_layer.observation_gate import check_and_prepare

    msg = _make_message()
    return _measure("完整语义网关", lambda: check_and_prepare(msg), runs)


def _find_bindings() -> Optional[str]:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "bindings.ttl"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return None


def stage_binding_load(runs: int) -> Latency:
    from semantic_layer.protocol_binding import BindingRegistry

    ttl = _find_bindings()
    if ttl is None:
        return Latency("本体加载与校验")

    def load():
        BindingRegistry().load_turtle(ttl)

    return _measure("本体加载与校验", load, runs)


def stage_adapter_generation(runs: int) -> Latency:
    from semantic_layer.protocol_binding import BindingRegistry, generate_all

    ttl = _find_bindings()
    if ttl is None:
        return Latency("适配代码生成")
    registry = BindingRegistry()
    registry.load_turtle(ttl)
    if len(registry) == 0:
        return Latency("适配代码生成")

    return _measure("适配代码生成", lambda: generate_all(registry), runs)


LATENCY_STAGES = [
    stage_rdf_mapping,
    stage_shacl_structural,
    stage_shacl_domain,
    stage_unit_harmonizer,
    stage_full_gate,
    stage_binding_load,
    stage_adapter_generation,
]


@dataclass
class ResourceUse:
    available: bool
    cpu_percent: float = 0.0
    cpu_seconds: float = 0.0
    rss_start_mb: float = 0.0
    rss_end_mb: float = 0.0
    rss_peak_mb: float = 0.0
    threads: int = 0
    note: str = ""


def measure_resources(runs: int) -> ResourceUse:
    if psutil is None:
        return ResourceUse(
            available=False,
            note="psutil 未安装，跳过资源测量（pip install psutil）",
        )

    from semantic_layer.observation_gate import check_and_prepare

    proc = psutil.Process(os.getpid())
    msg = _make_message()

    gc.collect()
    rss_start = proc.memory_info().rss / 1_048_576
    peak = rss_start
    cpu_before = proc.cpu_times()
    wall_start = time.perf_counter()

    for i in range(runs):
        check_and_prepare(msg)
        if i % 50 == 0:
            peak = max(peak, proc.memory_info().rss / 1_048_576)

    wall = time.perf_counter() - wall_start
    cpu_after = proc.cpu_times()
    gc.collect()
    rss_end = proc.memory_info().rss / 1_048_576
    peak = max(peak, rss_end)

    cpu_seconds = (
        cpu_after.user - cpu_before.user + cpu_after.system - cpu_before.system
    )

    return ResourceUse(
        available=True,
        cpu_percent=(cpu_seconds / wall * 100.0) if wall > 0 else 0.0,
        cpu_seconds=cpu_seconds,
        rss_start_mb=rss_start,
        rss_end_mb=rss_end,
        rss_peak_mb=peak,
        threads=proc.num_threads(),
    )


@dataclass
class Stability:
    duration_s: float
    iterations: int
    failures: int
    rss_start_mb: float
    rss_end_mb: float
    drift_mb_per_min: float
    p95_first_quarter_ms: float
    p95_last_quarter_ms: float
    drift_ratio: float
    verdict: str


def measure_stability(duration_s: float) -> Optional[Stability]:
    if duration_s <= 0:
        return None

    from semantic_layer.observation_gate import check_and_prepare

    msg = _make_message()
    proc = psutil.Process(os.getpid()) if psutil else None

    gc.collect()
    for _ in range(50):
        check_and_prepare(msg)
    gc.collect()
    rss_start = proc.memory_info().rss / 1_048_576 if proc else 0.0

    samples: list[float] = []
    failures = 0
    start = time.perf_counter()
    while time.perf_counter() - start < duration_s:
        t0 = time.perf_counter()
        try:
            check_and_prepare(msg)
        except Exception:
            failures += 1
            continue
        samples.append((time.perf_counter() - t0) * 1000.0)

    elapsed = time.perf_counter() - start
    gc.collect()
    rss_end = proc.memory_info().rss / 1_048_576 if proc else 0.0

    quarter = max(1, len(samples) // 4)
    first = sorted(samples[:quarter])
    last = sorted(samples[-quarter:])
    p95_first = first[min(len(first) - 1, int(0.95 * len(first)))] if first else 0.0
    p95_last = last[min(len(last) - 1, int(0.95 * len(last)))] if last else 0.0
    ratio = (p95_last / p95_first) if p95_first > 0 else 0.0
    drift = ((rss_end - rss_start) / elapsed * 60.0) if elapsed > 0 else 0.0

    if failures > 0:
        verdict = f"出现 {failures} 次失败"
    elif drift > 2.0:
        verdict = "内存持续增长，需进一步观察"
    elif ratio > 1.5:
        verdict = "延迟随时间上升"
    else:
        verdict = "稳定"

    return Stability(
        duration_s=elapsed,
        iterations=len(samples),
        failures=failures,
        rss_start_mb=rss_start,
        rss_end_mb=rss_end,
        drift_mb_per_min=drift,
        p95_first_quarter_ms=p95_first,
        p95_last_quarter_ms=p95_last,
        drift_ratio=ratio,
        verdict=verdict,
    )


async def measure_fuseki_write(runs: int, url: str) -> Latency:
    import httpx
    from semantic_layer.fuseki import to_turtle

    result = Latency("Fuseki 写入")
    turtle = to_turtle(_make_message()).encode("utf-8")
    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        for _ in range(runs):
            t0 = time.perf_counter()
            try:
                resp = await client.post(
                    url, content=turtle, headers={"Content-Type": "text/turtle"}
                )
                if resp.status_code >= 300:
                    result.failures += 1
                    continue
            except Exception:
                result.failures += 1
                continue
            result.samples.append((time.perf_counter() - t0) * 1000.0)
    return result


async def measure_sparql_query(runs: int, url: str) -> Latency:
    import httpx

    result = Latency("SPARQL 查询")
    query = "SELECT * WHERE {?s ?p ?o} LIMIT 50"
    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        for _ in range(runs):
            t0 = time.perf_counter()
            try:
                resp = await client.post(
                    url,
                    content=query.encode("utf-8"),
                    headers={
                        "Content-Type": "application/sparql-query",
                        "Accept": "application/sparql-results+json",
                    },
                )
                if resp.status_code >= 300:
                    result.failures += 1
                    continue
            except Exception:
                result.failures += 1
                continue
            result.samples.append((time.perf_counter() - t0) * 1000.0)
    return result


def _bar(value: float, ceiling: float, width: int = 18) -> str:
    if ceiling <= 0:
        return "." * width
    filled = min(width, int(round(value / ceiling * width)))
    return "#" * filled + "." * (width - filled)


def print_report(
    latencies: list[Latency],
    resources: ResourceUse,
    stability: Optional[Stability],
    runs: int,
    machine: dict,
) -> None:
    line = "-" * 78
    print()
    print("XA-202606 语义层性能测试")
    print(f"{machine['stamp']}   {machine['python']}   {machine['platform']}")
    print(f"每项 {runs} 次")
    print()

    print("一、处理延迟")
    print(line)
    print(
        f"{'阶段':<18}{'次数':>6}{'均值':>9}{'p50':>9}{'p95':>9}{'p99':>9}{'失败':>6}"
    )
    measured = [l for l in latencies if l.n > 0]
    ceiling = max((l.pct(0.95) for l in measured), default=1.0)
    for l in latencies:
        if l.n == 0:
            print(f"{l.name:<18}{'—':>6}{'跳过':>9}")
            continue
        print(
            f"{l.name:<18}{l.n:>6}{l.mean:>8.2f}ms{l.pct(0.50):>7.2f}ms"
            f"{l.pct(0.95):>7.2f}ms{l.pct(0.99):>7.2f}ms{l.failures:>6}"
        )
    print()
    for l in measured:
        print(f"  {l.name:<18}{_bar(l.pct(0.95), ceiling)}  p95 {l.pct(0.95):.2f}ms")
    print()

    print("二、CPU 占用")
    print(line)
    if not resources.available:
        print(f"  {resources.note}")
    else:
        print(f"  单核占用率      {resources.cpu_percent:.1f}%")
        print(f"  CPU 时间        {resources.cpu_seconds:.3f}s")
        print(f"  线程数          {resources.threads}")
    print()

    print("三、内存占用")
    print(line)
    if not resources.available:
        print(f"  {resources.note}")
    else:
        print(f"  起始 RSS        {resources.rss_start_mb:.1f} MB")
        print(f"  结束 RSS        {resources.rss_end_mb:.1f} MB")
        print(f"  峰值 RSS        {resources.rss_peak_mb:.1f} MB")
        print(
            f"  净增长          {resources.rss_end_mb - resources.rss_start_mb:+.2f} MB"
        )
    print()

    print("四、连续运行稳定性")
    print(line)
    if stability is None:
        print("  未运行（使用 --soak <秒> 开启）")
    else:
        print(f"  运行时长        {stability.duration_s:.1f}s")
        print(f"  处理报文        {stability.iterations}")
        print(f"  失败            {stability.failures}")
        print(
            f"  内存漂移        {stability.drift_mb_per_min:+.3f} MB/min "
            f"({stability.rss_start_mb:.1f} → {stability.rss_end_mb:.1f} MB)"
        )
        print(
            f"  延迟漂移        前 1/4 p95 {stability.p95_first_quarter_ms:.2f}ms → "
            f"后 1/4 p95 {stability.p95_last_quarter_ms:.2f}ms "
            f"(×{stability.drift_ratio:.2f})"
        )
        print(f"  结论            {stability.verdict}")
    print()


def write_files(
    latencies: list[Latency],
    resources: ResourceUse,
    stability: Optional[Stability],
    output: Path,
    machine: dict,
) -> None:
    payload = {
        "machine": machine,
        "latency": [l.row() for l in latencies],
        "cpu": {
            "available": resources.available,
            "percent_of_one_core": round(resources.cpu_percent, 2),
            "cpu_seconds": round(resources.cpu_seconds, 4),
            "threads": resources.threads,
        },
        "memory": {
            "available": resources.available,
            "rss_start_mb": round(resources.rss_start_mb, 2),
            "rss_end_mb": round(resources.rss_end_mb, 2),
            "rss_peak_mb": round(resources.rss_peak_mb, 2),
        },
        "stability": None
        if stability is None
        else {
            "duration_s": round(stability.duration_s, 2),
            "iterations": stability.iterations,
            "failures": stability.failures,
            "drift_mb_per_min": round(stability.drift_mb_per_min, 4),
            "p95_first_quarter_ms": round(stability.p95_first_quarter_ms, 3),
            "p95_last_quarter_ms": round(stability.p95_last_quarter_ms, 3),
            "drift_ratio": round(stability.drift_ratio, 3),
            "verdict": stability.verdict,
        },
    }
    output.with_suffix(".json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rows = [l.row() for l in latencies if l.n > 0]
    if rows:
        with output.with_suffix(".csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    print(
        f"  写入 {output.with_suffix('.json').name} 和 "
        f"{output.with_suffix('.csv').name}"
    )
    print()


async def _main() -> int:
    parser = argparse.ArgumentParser(description="语义层性能测试")
    parser.add_argument("--runs", type=int, default=200)
    parser.add_argument("--soak", type=float, default=0.0, help="连续运行秒数")
    parser.add_argument("--fuseki", type=str, default=None)
    parser.add_argument("--output", type=str, default="benchmark_results")
    args = parser.parse_args()

    import platform

    machine = {
        "stamp": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M"),
        "python": f"Python {platform.python_version()}",
        "platform": f"{platform.system()} {platform.release()}",
    }

    latencies = [stage(args.runs) for stage in LATENCY_STAGES]

    if args.fuseki:
        base = args.fuseki.rstrip("/")
        latencies.append(await measure_fuseki_write(args.runs, f"{base}/data?default"))
        latencies.append(await measure_sparql_query(args.runs, f"{base}/query"))

    resources = measure_resources(args.runs)
    stability = measure_stability(args.soak)

    print_report(latencies, resources, stability, args.runs, machine)
    write_files(latencies, resources, stability, Path(args.output), machine)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
