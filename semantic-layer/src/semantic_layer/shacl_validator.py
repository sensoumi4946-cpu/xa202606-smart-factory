"""Compatibility facade over the canonical SHACL runner.

Older callers used tuple/string helpers.  Keeping this facade avoids two
independent validation implementations while preserving that public API.
"""

from rdflib import RDF, SOSA, Graph

from semantic_layer.shacl_runner import validate


def validate_observation_graph(graph: Graph) -> tuple[bool, list[str]]:
    report = validate(graph)
    return report.conforms, [*report.violations, *report.warnings]


def validate_and_explain(graph: Graph) -> str:
    report = validate(graph)
    if report.conforms:
        count = sum(1 for _ in graph.subjects(RDF.type, SOSA.Observation))
        return f"✓ — {count} observation(s) passed all checks."
    errors = report.violations or report.warnings
    return "\n".join(
        [f"✗ — {len(errors)} violation(s):", *(f"  • {error}" for error in errors)]
    )
