"""
Performance characterisation of semantic interoperability middleware.

Benchmarks:
  BM-1  mapping.to_rdf_graph()  — serialisation latency per message
  BM-2  shacl_runner.validate() — structural gate latency per message
  BM-3  shacl_domain_shapes    — domain gate latency per message
  BM-4  semantic_unit_harmonizer.enrich_graph_with_qudt() — enrichment
  BM-5  observation_gate.check_and_prepare() — full gate pipeline
  BM-6  write_to_fuseki()       — network write latency (requires live Fuseki)
  BM-7  sparql_templates queries via Fuseki (requires live Fuseki)
  BM-8  ontology_reasoner.reason() — RDFS inference overhead

Usage:
    python semantic_benchmark.py            # runs BM-1..BM-5 (no Fuseki needed)
    python semantic_benchmark.py --fuseki http://localhost:3030/factory
    python semantic_benchmark.py --runs 500 --output results/benchmark.json

Drop-in: semantic-layer/src/semantic_layer/ OR run standalone.
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import math
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Synthetic message factory

def _make_message(protocol: str = "modbus", subsystem: str = "gas"):
    from smart_factory_contracts.messages import (
        Measurement, MeasurementType, Protocol, Subsystem, Unit, UnifiedMessage,
    )
    _protocol_map = {
        "modbus": Protocol.MODBUS, "mqtt": Protocol.MQTT,
        "opcua": Protocol.OPCUA,   "rest": Protocol.REST,
    }
    _subsystem_map = {
        "gas": Subsystem.GAS, "temp_humidity": Subsystem.TEMP_HUMIDITY,
        "agv": Subsystem.AGV, "counting": Subsystem.COUNTING,
        "lighting": Subsystem.LIGHTING,
    }
    return UnifiedMessage(
        schema_version="v1",
        device_id="bench_sensor_01",
        subsystem=_subsystem_map.get(subsystem, Subsystem.GAS),
        protocol=_protocol_map.get(protocol, Protocol.MODBUS),
        timestamp=datetime.now(timezone.utc),
        measurements=[
            Measurement(type=MeasurementType.CO,          value=22.5, unit=Unit.PPM),
            Measurement(type=MeasurementType.SMOKE,       value=4.1,  unit=Unit.PPM),
            Measurement(type=MeasurementType.COMBUSTIBLE_GAS, value=1.2, unit=Unit.PPM),
        ],
    )


# Statistics

@dataclass
class BenchmarkResult:
    name: str
    runs: int
    times_ms: list[float] = field(default_factory=list)

    @property
    def mean_ms(self) -> float:
        return statistics.mean(self.times_ms) if self.times_ms else 0.0

    @property
    def median_ms(self) -> float:
        return statistics.median(self.times_ms) if self.times_ms else 0.0

    @property
    def p95_ms(self) -> float:
        if not self.times_ms:
            return 0.0
        s = sorted(self.times_ms)
        idx = max(0, int(math.ceil(0.95 * len(s))) - 1)
        return s[idx]

    @property
    def std_ms(self) -> float:
        return statistics.stdev(self.times_ms) if len(self.times_ms) > 1 else 0.0

    def to_dict(self) -> dict:
        return {
            "benchmark": self.name,
            "runs": self.runs,
            "mean_ms": round(self.mean_ms, 3),
            "median_ms": round(self.median_ms, 3),
            "p95_ms": round(self.p95_ms, 3),
            "std_ms": round(self.std_ms, 3),
        }

    def summary_line(self) -> str:
        return (
            f"[{self.name}] "
            f"mean={self.mean_ms:.2f}ms  "
            f"median={self.median_ms:.2f}ms  "
            f"p95={self.p95_ms:.2f}ms  "
            f"std={self.std_ms:.2f}ms  "
            f"(n={self.runs})"
        )


def _time_fn(fn: Callable, runs: int) -> list[float]:
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return times


# Individual benchmarks

def bm1_mapping(runs: int) -> BenchmarkResult:
    from semantic_layer.mapping import to_rdf_graph
    msg = _make_message()
    result = BenchmarkResult("BM1_mapping", runs)
    result.times_ms = _time_fn(lambda: to_rdf_graph(msg), runs)
    return result


def bm2_shacl_structural(runs: int) -> BenchmarkResult:
    from semantic_layer.mapping import to_rdf_graph
    from semantic_layer.shacl_runner import validate
    msg = _make_message()
    g = to_rdf_graph(msg)
    result = BenchmarkResult("BM2_shacl_structural", runs)
    result.times_ms = _time_fn(lambda: validate(g), runs)
    return result


def bm3_shacl_domain(runs: int) -> BenchmarkResult:
    from semantic_layer.mapping import to_rdf_graph
    try:
        from semantic_layer.shacl_domain_shapes import load_all_shapes
        import pyshacl
        msg = _make_message()
        g = to_rdf_graph(msg)
        shapes = load_all_shapes()

        def run_domain():
            pyshacl.validate(g, shacl_graph=shapes, inference="none", abort_on_first=False)

        result = BenchmarkResult("BM3_shacl_domain", runs)
        result.times_ms = _time_fn(run_domain, runs)
    except ImportError:
        logger.warning("BM3 skipped: pyshacl or shacl_domain_shapes not available")
        result = BenchmarkResult("BM3_shacl_domain_SKIPPED", 0)
    return result


def bm4_unit_harmonizer(runs: int) -> BenchmarkResult:
    from semantic_layer.mapping import to_rdf_graph
    try:
        from semantic_layer.semantic_unit_harmonizer import enrich_graph_with_qudt
        msg = _make_message()
        g = to_rdf_graph(msg)
        result = BenchmarkResult("BM4_unit_harmonizer", runs)
        result.times_ms = _time_fn(lambda: enrich_graph_with_qudt(g.parse(data=g.serialize())), runs)
    except ImportError:
        result = BenchmarkResult("BM4_unit_harmonizer_SKIPPED", 0)
    return result


def bm5_full_gate(runs: int) -> BenchmarkResult:
    from semantic_layer.observation_gate import check_and_prepare
    msg = _make_message()
    result = BenchmarkResult("BM5_full_gate", runs)
    result.times_ms = _time_fn(lambda: check_and_prepare(msg), runs)
    return result


def bm8_reasoner(runs: int) -> BenchmarkResult:
    from semantic_layer.mapping import to_rdf_graph
    try:
        from semantic_layer.ontology_reasoner import reason
        msg = _make_message()
        g = to_rdf_graph(msg)
        result = BenchmarkResult("BM8_rdfs_inference", runs)
        result.times_ms = _time_fn(lambda: reason(g), runs)
    except ImportError:
        result = BenchmarkResult("BM8_rdfs_inference_SKIPPED", 0)
    return result


# Async Fuseki benchmarks

async def bm6_fuseki_write(runs: int, fuseki_data_url: str) -> BenchmarkResult:
    from semantic_layer.fuseki import write_to_fuseki
    msg = _make_message()
    result = BenchmarkResult("BM6_fuseki_write", runs)
    for _ in range(runs):
        t0 = time.perf_counter()
        await write_to_fuseki(msg, fuseki_data_url)
        result.times_ms.append((time.perf_counter() - t0) * 1000)
    return result


async def bm7_sparql_query(runs: int, fuseki_query_url: str) -> BenchmarkResult:
    import httpx
    from semantic_layer.sparql_templates import subsystem_summary
    query = subsystem_summary()
    result = BenchmarkResult("BM7_sparql_query", runs)

    async with httpx.AsyncClient(timeout=10.0) as client:
        for _ in range(runs):
            t0 = time.perf_counter()
            try:
                await client.post(
                    fuseki_query_url,
                    content=query.encode(),
                    headers={
                        "Content-Type": "application/sparql-query",
                        "Accept": "application/sparql-results+json",
                    },
                )
            except httpx.HTTPError:
                pass
            result.times_ms.append((time.perf_counter() - t0) * 1000)
    return result


# Report writer

def write_report(results: list[BenchmarkResult], output_path: Path) -> None:
    data = [r.to_dict() for r in results if r.runs > 0]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    json_path = output_path.with_suffix(".json")
    json_path.write_text(json.dumps(data, indent=2))
    logger.info("JSON report: %s", json_path)

    csv_path = output_path.with_suffix(".csv")
    if data:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            writer.writeheader()
            writer.writerows(data)
        logger.info("CSV report:  %s", csv_path)


# CLI entrypoint

async def _main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Semantic pipeline benchmark")
    parser.add_argument("--runs",    type=int,  default=200,
                        help="Iterations per benchmark (default 200)")
    parser.add_argument("--fuseki", type=str, default=None,
                        help="Fuseki base URL, e.g. http://localhost:3030/factory")
    parser.add_argument("--output", type=str, default="benchmark_results",
                        help="Output file path (without extension)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    results: list[BenchmarkResult] = []
    print(f"\n{'='*60}")
    print(f"  Semantic Pipeline Benchmark  ({args.runs} runs each)")
    print(f"{'='*60}\n")

    for bm_fn in [bm1_mapping, bm2_shacl_structural, bm3_shacl_domain,
                  bm4_unit_harmonizer, bm5_full_gate, bm8_reasoner]:
        try:
            r = bm_fn(args.runs)
            results.append(r)
            print(r.summary_line())
        except Exception as exc:
            print(f"[{bm_fn.__name__}] ERROR: {exc}")

    if args.fuseki:
        data_url  = f"{args.fuseki}/data"
        query_url = f"{args.fuseki}/query"
        print(f"\nFuseki benchmarks → {args.fuseki}")
        for bm_fn, url in [(bm6_fuseki_write, data_url), (bm7_sparql_query, query_url)]:
            try:
                r = await bm_fn(args.runs, url)
                results.append(r)
                print(r.summary_line())
            except Exception as exc:
                print(f"[{bm_fn.__name__}] ERROR: {exc}")

    print()
    write_report(results, Path(args.output))
    print("Done.")


if __name__ == "__main__":
    asyncio.run(_main())
