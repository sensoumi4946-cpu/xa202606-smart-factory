"""Check the boundary of the repository's ontology extensibility claim.

This benchmark deliberately tests a *new measurement type*, not merely whether
Turtle syntax can be parsed. The platform uses a strict UnifiedMessage
contract, so an ontology-only vibration extension must be rejected until the
contract and semantic mappings are extended as well.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from rdflib import Graph
from smart_factory_contracts.messages import MeasurementType


@dataclass
class ExtensionCheck:
    approach: str
    sensor_type: str
    ontology_lines: int
    ontology_triples: int
    ontology_only_supported: bool
    restart_required: bool
    validation_kept: bool
    elapsed_seconds: float
    notes: str


NEW_SENSOR_TURTLE = """
@prefix sf:   <http://example.org/smart-factory#> .
@prefix sosa: <http://www.w3.org/ns/sosa/> .
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
    return len([line for line in text.strip().splitlines() if line.strip()])


def measure_semantic_approach() -> ExtensionCheck:
    start = time.perf_counter()
    graph = Graph()
    graph.parse(data=NEW_SENSOR_TURTLE, format="turtle")

    try:
        MeasurementType("vibration")
        supported = True
    except ValueError:
        supported = False

    return ExtensionCheck(
        approach="ontology_only",
        sensor_type="vibration",
        ontology_lines=_count_lines(NEW_SENSOR_TURTLE),
        ontology_triples=len(graph),
        ontology_only_supported=supported,
        restart_required=True,
        validation_kept=True,
        elapsed_seconds=time.perf_counter() - start,
        notes=(
            "The graph parses, but UnifiedMessage rejects vibration. A genuine "
            "new type requires coordinated contract, mapping, shape/rule, and "
            "test changes; parsing Turtle alone is not runtime extensibility."
        ),
    )


def measure_baseline_approach() -> ExtensionCheck:
    from benchmark.baseline_platform import EXTENSION_DIFF

    return ExtensionCheck(
        approach="explicit_code_baseline",
        sensor_type="vibration",
        ontology_lines=0,
        ontology_triples=0,
        ontology_only_supported=False,
        restart_required=True,
        validation_kept=False,
        elapsed_seconds=float("nan"),
        notes=(
            f"Illustrative baseline lists {len(EXTENSION_DIFF)} explicit edits. "
            "It is not a measured external product benchmark."
        ),
    )


def run() -> dict[str, Any]:
    semantic = measure_semantic_approach()
    baseline = measure_baseline_approach()
    return {
        "benchmark": "BM-EXT-1 ontology-only new measurement type",
        "results": [asdict(semantic), asdict(baseline)],
        "summary": {
            "ontology_only_supported": semantic.ontology_only_supported,
            "validation_rejects_unknown_type": not semantic.ontology_only_supported,
            "restart_required": semantic.restart_required,
            "finding": (
                "The platform is binding-extensible for known measurement types, "
                "but it is not ontology-only extensible for new types."
            ),
        },
    }


def render(result: dict[str, Any]) -> str:
    summary = result["summary"]
    return "\n".join(
        [
            "",
            "  BM-EXT-1  Ontology-only new type: vibration",
            "  " + "-" * 58,
            f"  accepted by runtime contract: {summary['ontology_only_supported']}",
            f"  validation rejects unknown type: {summary['validation_rejects_unknown_type']}",
            f"  service restart after code extension: {summary['restart_required']}",
            f"  finding: {summary['finding']}",
            "",
        ]
    )


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
