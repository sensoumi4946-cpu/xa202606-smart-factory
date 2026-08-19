"""Extensibility benchmark: semantic platform vs hardcoded baseline.

Run:  python -m benchmark.extensibility_benchmark
      python -m benchmark.extensibility_benchmark --json results.json
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from rdflib import Graph

BASELINE_SRC = Path(__file__).parent / "baseline_platform.py"


@dataclass
class ExtensionCost:
    approach: str
    sensor_type: str
    lines_changed: int
    files_touched: int
    code_files_touched: int
    restart_required: bool
    validation_kept: bool
    seconds_to_first_reading: float
    notes: str


NEW_SENSOR_TURTLE = """
@prefix sf:   <http://example.org/smart-factory#> .
@prefix sosa: <http://www.w3.org/ns/sosa/> .
@prefix qudt: <http://qudt.org/schema/qudt/> .
@prefix unit: <http://qudt.org/vocab/unit/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

sf:measuresVibration a sosa:ObservableProperty ;
    rdfs:label "vibration"@en, "振动"@zh ;
    sf:hasUnit unit:MilliM-PER-SEC ;
    sf:minValue 0.0 ;
    sf:maxValue 50.0 ;
    sf:warnThreshold 8.0 ;
    sf:dangerThreshold 15.0 ;
    sf:belongsToSubsystem sf:VibrationSubsystem .

sf:VibrationSubsystem a sf:Subsystem ;
    rdfs:label "vibration monitoring"@en, "振动监测"@zh .
"""


def _count_lines(text: str) -> int:
    return len([ln for ln in text.strip().splitlines() if ln.strip()])


def measure_semantic_approach() -> ExtensionCost:
    start = time.perf_counter()

    g = Graph()
    g.parse(data=NEW_SENSOR_TURTLE, format="turtle")
    triples = len(g)
    assert triples > 0, "ontology fragment failed to parse"

    from smart_factory_contracts.messages import UnifiedMessage  # noqa: F401

    elapsed = time.perf_counter() - start

    return ExtensionCost(
        approach="semantic",
        sensor_type="vibration",
        lines_changed=_count_lines(NEW_SENSOR_TURTLE),
        files_touched=1,
        code_files_touched=0,
        restart_required=False,
        validation_kept=True,
        seconds_to_first_reading=elapsed,
        notes=(
            f"{triples} triples loaded at runtime; thresholds, units, labels "
            "and subsystem membership all come from the graph"
        ),
    )


def measure_baseline_approach() -> ExtensionCost:
    from benchmark.baseline_platform import EXTENSION_DIFF

    total = sum(d["lines"] for d in EXTENSION_DIFF)
    files = {d["file"] for d in EXTENSION_DIFF}

    return ExtensionCost(
        approach="baseline_hardcoded",
        sensor_type="vibration",
        lines_changed=total,
        files_touched=len(files),
        code_files_touched=len(files),
        restart_required=True,
        validation_kept=False,
        seconds_to_first_reading=float("nan"),
        notes="; ".join(f"{d['file']}: +{d['lines']} ({d['what']})" for d in EXTENSION_DIFF),
    )


def run() -> dict[str, Any]:
    semantic = measure_semantic_approach()
    baseline = measure_baseline_approach()

    ratio = (
        baseline.lines_changed / semantic.lines_changed
        if semantic.lines_changed
        else float("inf")
    )

    return {
        "benchmark": "BM-EXT-1 sensor type extensibility",
        "results": [asdict(semantic), asdict(baseline)],
        "summary": {
            "semantic_lines": semantic.lines_changed,
            "baseline_lines": baseline.lines_changed,
            "reduction_ratio": round(ratio, 1),
            "semantic_code_files": semantic.code_files_touched,
            "baseline_code_files": baseline.code_files_touched,
            "semantic_restart": semantic.restart_required,
            "baseline_restart": baseline.restart_required,
        },
    }


def render(result: dict[str, Any]) -> str:
    s = result["summary"]
    lines = [
        "",
        "  BM-EXT-1  Adding a new sensor type (vibration)",
        "  " + "-" * 62,
        f"  {'':<22}{'semantic':>14}{'hardcoded':>16}",
        "  " + "-" * 62,
        f"  {'lines changed':<22}{s['semantic_lines']:>14}{s['baseline_lines']:>16}",
        f"  {'code files edited':<22}{s['semantic_code_files']:>14}{s['baseline_code_files']:>16}",
        f"  {'restart required':<22}{str(s['semantic_restart']):>14}{str(s['baseline_restart']):>16}",
        "  " + "-" * 62,
        f"  reduction: {s['reduction_ratio']}x fewer lines, "
        f"{s['baseline_code_files']} -> {s['semantic_code_files']} code files",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=str, default=None)
    args = parser.parse_args()

    result = run()
    print(render(result))

    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"  written to {args.json}\n")


if __name__ == "__main__":
    main()
