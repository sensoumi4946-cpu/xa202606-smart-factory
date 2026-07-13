# Observation gate validates RDF before Fuseki write.

from datetime import datetime, timezone

from rdflib import Graph, Literal, Namespace, URIRef, XSD

from semantic_layer.mapping import SF, to_rdf_graph
from semantic_layer.shacl_runner import ValidationReport, validate

from smart_factory_contracts.messages import UnifiedMessage

PROV = Namespace("http://www.w3.org/ns/prov#")
_SF = Namespace(SF)


def _add_provenance(g: Graph, msg: UnifiedMessage) -> None:
    
    from rdflib import RDF, SOSA

    g.bind("prov", PROV)

    # the adapter is modeled as a prov:SoftwareAgent
    adapter_uri = URIRef(f"{SF}adapter_{msg.protocol.value}")
    g.add((adapter_uri, RDF.type, PROV.SoftwareAgent))
    g.add((adapter_uri, _SF.protocol, Literal(msg.protocol.value)))

    now_str = datetime.now(timezone.utc).isoformat()

    for obs in g.subjects(RDF.type, SOSA.Observation):
        # prov:wasGeneratedBy links the observation to the ingestion event
        g.add((obs, PROV.wasAttributedTo, adapter_uri))
        g.add((obs, PROV.generatedAtTime,
               Literal(now_str, datatype=XSD.dateTime)))


class GateResult:

    def __init__(self, accepted: bool, graph: Graph | None,
                 report: ValidationReport):
        self.accepted = accepted
        self.graph = graph
        self.report = report

    @property
    def turtle(self) -> str | None:
        if self.graph is None:
            return None
        from rdflib import SOSA
        self.graph.bind("sosa", SOSA)
        self.graph.bind("sf", _SF)
        self.graph.bind("prov", PROV)
        return self.graph.serialize(format="turtle")


def check_and_prepare(msg: UnifiedMessage,
                      add_prov: bool = True) -> GateResult:
    g = to_rdf_graph(msg)

    report = validate(g)

    if not report.conforms:
        return GateResult(accepted=False, graph=None, report=report)

    if add_prov:
        _add_provenance(g, msg)

    return GateResult(accepted=True, graph=g, report=report)
