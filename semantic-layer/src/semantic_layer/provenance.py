"""Reusable W3C PROV-O helpers for sensor and processing provenance."""

from __future__ import annotations

from datetime import datetime, timezone

from rdflib import RDF, RDFS, SOSA, XSD, Graph, Literal, Namespace, URIRef

SF = Namespace("http://example.org/smart-factory#")
PROV = Namespace("http://www.w3.org/ns/prov#")


def stamp_provenance(
    graph: Graph,
    protocol: str,
    device_id: str,
    ingested_at: datetime | None = None,
) -> Graph:
    graph.bind("prov", PROV)
    timestamp = ingested_at or datetime.now(timezone.utc)
    timestamp_literal = Literal(timestamp.isoformat(), datatype=XSD.dateTime)
    agent = URIRef(f"{SF}adapter_{protocol}")
    device = URIRef(f"{SF}{device_id}")

    graph.add((agent, RDF.type, PROV.SoftwareAgent))
    graph.add((agent, SF.protocol, Literal(protocol)))
    graph.add((agent, PROV.actedOnBehalfOf, device))
    for observation in graph.subjects(RDF.type, SOSA.Observation):
        graph.add((observation, PROV.wasAttributedTo, agent))
        graph.add((observation, PROV.generatedAtTime, timestamp_literal))
    return graph


def build_activity(
    graph: Graph,
    activity_id: str,
    started: datetime,
    ended: datetime | None = None,
    label: str = "",
) -> URIRef:
    activity = URIRef(f"{SF}activity_{activity_id}")
    graph.add((activity, RDF.type, PROV.Activity))
    graph.add(
        (activity, PROV.startedAtTime, Literal(started.isoformat(), datatype=XSD.dateTime))
    )
    if ended is not None:
        graph.add(
            (activity, PROV.endedAtTime, Literal(ended.isoformat(), datatype=XSD.dateTime))
        )
    if label:
        graph.add((activity, RDFS.label, Literal(label)))
    return activity
