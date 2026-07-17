# SHACL validation runner

from pathlib import Path
from dataclasses import dataclass, field

from rdflib import Graph

_SHAPES_PATH = Path(__file__).parent / "shapes" / "observation_shapes.ttl"

_shapes_cache: Graph | None = None


def _load_all_shapes() -> Graph:
    global _shapes_cache
    if _shapes_cache is not None:
        return _shapes_cache
    g = Graph()
    g.parse(str(_SHAPES_PATH), format="turtle")
    _shapes_cache = g
    return g


@dataclass
class ValidationReport:
    """Result of running SHACL validation on a data graph."""
    conforms: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.conforms and not self.warnings:
            return f"✓ SHACL validation passed"
        elif self.conforms:
            # passed but has warnings (sh:Warning severity)
            return f"✓ passed with {len(self.warnings)} warning(s)"
        else:
            return f"✗ {len(self.violations)} violation(s)"


def validate(data_graph: Graph) -> ValidationReport:
    
    try:
        import pyshacl
    except ImportError:
        return _fallback_validate(data_graph)

    shapes = _load_all_shapes()

    _result = pyshacl.validate(
        data_graph,
        shacl_graph=shapes,
        inference="none",
        abort_on_first=False,
    )
    conforms = bool(_result[0])
    results_graph = _result[1]
    assert isinstance(results_graph, Graph)

    report = ValidationReport(conforms=conforms)

    SH = "http://www.w3.org/ns/shacl#"
    from rdflib import URIRef
    from rdflib.namespace import RDF
    result_class = URIRef(f"{SH}ValidationResult")
    severity_prop = URIRef(f"{SH}resultSeverity")
    message_prop = URIRef(f"{SH}resultMessage")
    warning_sev = URIRef(f"{SH}Warning")

    for result_node in results_graph.subjects(RDF.type, result_class):
        msg_literals = list(results_graph.objects(result_node, message_prop))
        msg = str(msg_literals[0]) if msg_literals else "(no message)"

        severities = list(results_graph.objects(result_node, severity_prop))
        if severities and severities[0] == warning_sev:
            report.warnings.append(msg)
        else:
            report.violations.append(msg)

    return report


def _fallback_validate(data_graph: Graph) -> ValidationReport:

    from rdflib import RDF, SOSA

    report = ValidationReport(conforms=True)

    observations = list(data_graph.subjects(RDF.type, SOSA.Observation))
    if not observations:
        report.conforms = False
        report.violations.append("No sosa:Observation nodes found in graph")
        return report

    for obs in observations:
        label = str(obs).rsplit("#", 1)[-1] if "#" in str(obs) else str(obs)

        if not list(data_graph.objects(obs, SOSA.madeBySensor)):
            report.violations.append(f"{label}: missing sosa:madeBySensor")
        if not list(data_graph.objects(obs, SOSA.observedProperty)):
            report.violations.append(f"{label}: missing sosa:observedProperty")
        if not list(data_graph.objects(obs, SOSA.hasSimpleResult)):
            report.violations.append(f"{label}: missing sosa:hasSimpleResult")
        if not list(data_graph.objects(obs, SOSA.resultTime)):
            report.violations.append(f"{label}: missing sosa:resultTime")

    if report.violations:
        report.conforms = False

    return report

def validate_with_domain(data_graph: Graph) -> ValidationReport:
   # Used by semantic_benchmark.py BM-3
   from rdflib import URIRef
   try:
        from semantic_layer.shacl_domain_shapes import load_domain_shapes
        combined = Graph()
        combined += _load_all_shapes()
        combined += load_domain_shapes()
        import pyshacl
        _result = pyshacl.validate(
            data_graph, shacl_graph=combined, inference="none", abort_on_first=False
        )
        conforms = bool(_result[0])
        results_graph = _result[1]
        assert isinstance(results_graph, Graph)
        report = ValidationReport(conforms=conforms)
        
        SH = "http://www.w3.org/ns/shacl#"
        result_class  = URIRef(f"{SH}ValidationResult")
        severity_prop = URIRef(f"{SH}resultSeverity")
        message_prop  = URIRef(f"{SH}resultMessage")
        warning_sev   = URIRef(f"{SH}Warning")
        from rdflib.namespace import RDF
        for node in results_graph.subjects(RDF.type, result_class):
            msgs = list(results_graph.objects(node, message_prop))
            msg_text = str(msgs[0]) if msgs else "(no message)"
            sevs = list(results_graph.objects(node, severity_prop))
            if sevs and sevs[0] == warning_sev:
                report.warnings.append(msg_text)
            else:
                report.violations.append(msg_text)
        return report
   except ImportError:
        return validate(data_graph)
