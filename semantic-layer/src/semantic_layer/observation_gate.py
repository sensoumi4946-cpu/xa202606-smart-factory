# Observation gate validates RDF before Fuseki write.

from datetime import datetime, timezone

from rdflib import Graph, Literal, Namespace, URIRef, XSD
from rdflib.namespace import RDF, SOSA

from semantic_layer.mapping import SF, to_rdf_graph
from semantic_layer.shacl_runner import ValidationReport, validate
from semantic_layer.semantic_unit_harmonizer import enrich_graph_with_qudt
from semantic_layer.shacl_domain_shapes import load_all_shapes

from smart_factory_contracts.messages import UnifiedMessage

PROV = Namespace("http://www.w3.org/ns/prov#")
_SF = Namespace(SF)

_domain_shapes_cache = None


def _get_domain_shapes():
    global _domain_shapes_cache
    if _domain_shapes_cache is None:
        _domain_shapes_cache = load_all_shapes()
    return _domain_shapes_cache


def _add_provenance(g: Graph, msg: UnifiedMessage) -> None:
    g.bind("prov", PROV)
    adapter_uri = URIRef(f"{SF}adapter_{msg.protocol.value}")
    g.add((adapter_uri, RDF.type, PROV.SoftwareAgent))
    g.add((adapter_uri, _SF.protocol, Literal(msg.protocol.value)))
    now_str = datetime.now(timezone.utc).isoformat()
    for obs in g.subjects(RDF.type, SOSA.Observation):
        g.add((obs, PROV.wasAttributedTo, adapter_uri))
        g.add((obs, PROV.generatedAtTime, Literal(now_str, datatype=XSD.dateTime)))


class GateResult:
    def __init__(self, accepted: bool, graph: Graph | None, report: ValidationReport):
        self.accepted = accepted
        self.graph = graph
        self.report = report

    @property
    def turtle(self) -> str | None:
        if self.graph is None:
            return None
        self.graph.bind("sosa", SOSA)
        self.graph.bind("sf", _SF)
        self.graph.bind("prov", PROV)
        return self.graph.serialize(format="turtle")


def check_and_prepare(
    msg: UnifiedMessage,
    add_prov: bool = True,
    use_domain_shapes: bool = True,
) -> GateResult:
    
    g = to_rdf_graph(msg)

    
    enrich_graph_with_qudt(g)

    if use_domain_shapes:
        try:
            import pyshacl
            shapes = _get_domain_shapes()
            _result = pyshacl.validate(
                g,
                shacl_graph=shapes,
                inference="none",
                abort_on_first=False,
            )
            results_graph = _result[1]
            assert isinstance(results_graph, Graph)
            report = ValidationReport(conforms=True)
            SH = "http://www.w3.org/ns/shacl#"
            result_class  = URIRef(f"{SH}ValidationResult")
            severity_prop = URIRef(f"{SH}resultSeverity")
            message_prop  = URIRef(f"{SH}resultMessage")
            warning_sev   = URIRef(f"{SH}Warning")
            for node in results_graph.subjects(RDF.type, result_class):
                msgs = list(results_graph.objects(node, message_prop))
                msg_text = str(msgs[0]) if msgs else "(no message)"
                sevs = list(results_graph.objects(node, severity_prop))
                if sevs and sevs[0] == warning_sev:
                    report.warnings.append(msg_text)
                else:
                    report.violations.append(msg_text)
            report.conforms = len(report.violations) == 0
        except ImportError:
            report = validate(g)
    else:
        report = validate(g)

    if not report.conforms:
        return GateResult(accepted=False, graph=None, report=report)

    # stamp provenance
    if add_prov:
        _add_provenance(g, msg)

    return GateResult(accepted=True, graph=g, report=report)