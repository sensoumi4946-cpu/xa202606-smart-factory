"""Measure authenticated ingest latency and throughput against a running backend."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import statistics
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = REPO_ROOT / "data" / "samples" / "five_subsystems.jsonl"


def percentile(values: list[float], percent: float) -> float:
    if not values:
        raise ValueError("values must not be empty")
    ordered = sorted(values)
    index = max(0, math.ceil(percent / 100 * len(ordered)) - 1)
    return ordered[index]


def summarize(latencies_ms: list[float], errors: int, elapsed_s: float) -> dict:
    successful = len(latencies_ms)
    return {
        "requests": successful + errors,
        "successful": successful,
        "errors": errors,
        "error_rate": errors / (successful + errors) if successful + errors else 0.0,
        "throughput_rps": successful / elapsed_s if elapsed_s else 0.0,
        "latency_ms": {
            "min": min(latencies_ms) if latencies_ms else None,
            "mean": statistics.fmean(latencies_ms) if latencies_ms else None,
            "p50": percentile(latencies_ms, 50) if latencies_ms else None,
            "p95": percentile(latencies_ms, 95) if latencies_ms else None,
            "p99": percentile(latencies_ms, 99) if latencies_ms else None,
            "max": max(latencies_ms) if latencies_ms else None,
        },
        "elapsed_s": elapsed_s,
    }


def post(url: str, api_key: str, body: bytes, timeout: float) -> float:
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()
        if response.status >= 300:
            raise RuntimeError(f"HTTP {response.status}")
    return (time.perf_counter() - started) * 1000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/ingest/api/v1/data")
    parser.add_argument("--api-key", default=os.getenv("API_KEY", ""))
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.api_key:
        parser.error("--api-key or API_KEY is required")
    if args.requests < 1 or args.concurrency < 1:
        parser.error("--requests and --concurrency must be positive")

    bodies = [line.encode() for line in args.data.read_text().splitlines() if line]
    if not bodies:
        parser.error("data file is empty")
    workload = [bodies[index % len(bodies)] for index in range(args.requests)]
    latencies: list[float] = []
    errors = 0
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(args.concurrency) as executor:
        futures = [executor.submit(post, args.url, args.api_key, body, args.timeout) for body in workload]
        for future in concurrent.futures.as_completed(futures):
            try:
                latencies.append(future.result())
            except Exception:
                errors += 1
    elapsed = time.perf_counter() - started
    report = {
        "evidence_type": "measured_http_ingest",
        "data_classification": "synthetic_workload",
        "url": args.url,
        "concurrency": args.concurrency,
        **summarize(latencies, errors, elapsed),
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
