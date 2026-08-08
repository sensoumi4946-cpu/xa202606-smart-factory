# W3C PROV-O provenance tracking for sensor observations.

from datetime import datetime, timezone
from typing import Optional

from rdflib import RDF, SOSA, Graph, Literal, Namespace, URIRef, XSD

SF = Namespace("http://example.org/smart-factory#")
PROV = Namespace("http://www.w3.org/ns/prov#")


def stamp_provenance(
    graph: Graph,
    protocol: str,
    device_id: str,
    ingested_at: Optional[datetime] = None,
) -> Graph:
    
    graph.bind("prov", PROV)

    ts = ingested_at or datetime.now(timezone.utc)
    ts_literal = Literal(ts.isoformat(), datatype=XSD.dateTime)

    # one agent per protocol, reused across observations
    agent = URIRef(f"{SF}adapter_{protocol}")
    graph.add((agent, RDF.type, PROV.SoftwareAgent))
    graph.add((agent, SF.protocol, Literal(protocol)))

    # also link the agent to the device for traceability
    device_uri = URIRef(f"{SF}{device_id}")
    graph.add((agent, PROV.actedOnBehalfOf, device_uri))

    for obs in graph.subjects(RDF.type, SOSA.Observation):
        graph.add((obs, PROV.wasAttributedTo, agent))
        graph.add((obs, PROV.generatedAtTime, ts_literal))

    return graph


def build_activity(
    graph: Graph,
    activity_id: str,
    started: datetime,
    ended: Optional[datetime] = None,
    label: str = "",
) -> URIRef:
   
    activity = URIRef(f"{SF}activity_{activity_id}")
    graph.add((activity, RDF.type, PROV.Activity))
    graph.add((activity, PROV.startedAtTime,
               Literal(started.isoformat(), datatype=XSD.dateTime)))
    if ended:
        graph.add((activity, PROV.endedAtTime,
                   Literal(ended.isoformat(), datatype=XSD.dateTime)))
    if label:
        from rdflib import RDFS
        graph.add((activity, RDFS.label, Literal(label)))

    return activity
