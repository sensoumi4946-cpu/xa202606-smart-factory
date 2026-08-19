from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import XSD

logger = logging.getLogger(__name__)

SF = Namespace("http://example.org/smart-factory#")
SOSA = Namespace("http://www.w3.org/ns/sosa/")

META_SHAPE_TTL = """
@prefix sh:   <http://www.w3.org/ns/shacl#> .
@prefix sf:   <http://example.org/smart-factory#> .
@prefix sosa: <http://www.w3.org/ns/sosa/> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

sf:ObservablePropertyShape a sh:NodeShape ;
    sh:targetClass sosa:ObservableProperty ;
    sh:property [
        sh:path rdfs:label ;
        sh:minCount 1 ;
        sh:message "every property needs at least one rdfs:label" ;
    ] ;
    sh:property [
        sh:path sf:hasUnit ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:nodeKind sh:IRI ;
        sh:message "every property needs exactly one sf:hasUnit IRI" ;
    ] ;
    sh:property [
        sh:path sf:minValue ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:datatype xsd:double ;
        sh:message "sf:minValue must be a single xsd:double" ;
    ] ;
    sh:property [
        sh:path sf:maxValue ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:datatype xsd:double ;
        sh:message "sf:maxValue must be a single xsd:double" ;
    ] ;
    sh:property [
        sh:path sf:belongsToSubsystem ;
        sh:minCount 1 ;
        sh:nodeKind sh:IRI ;
        sh:message "every property must belong to a subsystem" ;
    ] .

sf:SubsystemShape a sh:NodeShape ;
    sh:targetClass sf:Subsystem ;
    sh:property [
        sh:path rdfs:label ;
        sh:minCount 1 ;
        sh:message "every subsystem needs at least one rdfs:label" ;
    ] .
"""


@dataclass
class PropertyDefinition:
    uri: str
    name: str
    labels: dict[str, str]
    unit: str
    min_value: float
    max_value: float
    subsystem: str
    warn_threshold: Optional[float] = None
    danger_threshold: Optional[float] = None
    direction: str = "high"

    def to_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "labels": self.labels,
            "unit": self.unit,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "subsystem": self.subsystem,
            "warn_threshold": self.warn_threshold,
            "danger_threshold": self.danger_threshold,
            "direction": self.direction,
        }


@dataclass
class LoadResult:
    accepted: bool
    version: str
    triples_added: int
    properties_added: list[str] = field(default_factory=list)
    subsystems_added: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    loaded_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "version": self.version,
            "triples_added": self.triples_added,
            "properties_added": self.properties_added,
            "subsystems_added": self.subsystems_added,
            "violations": self.violations,
            "loaded_at": self.loaded_at,
        }


def _local_name(uri: str) -> str:
    text = str(uri)
    if "#" in text:
        text = text.rsplit("#", 1)[-1]
    elif "/" in text:
        text = text.rsplit("/", 1)[-1]
    if text.startswith("measures"):
        text = text[len("measures") :]
    out = []
    for i, ch in enumerate(text):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def _float_or_none(graph: Graph, subject: URIRef, predicate: URIRef) -> Optional[float]:
    value = graph.value(subject, predicate)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_fragment(turtle: str) -> tuple[bool, list[str], Graph]:
    graph = Graph()
    try:
        graph.parse(data=turtle, format="turtle")
    except Exception as exc:
        return False, [f"turtle parse error: {exc}"], Graph()

    if len(graph) == 0:
        return False, ["fragment contains no triples"], graph

    has_property = any(graph.subjects(RDF.type, SOSA.ObservableProperty))
    has_subsystem = any(graph.subjects(RDF.type, SF.Subsystem))
    if not has_property and not has_subsystem:
        return (
            False,
            ["fragment declares no sosa:ObservableProperty and no sf:Subsystem"],
            graph,
        )

    try:
        import pyshacl
    except ImportError:
        return True, [], graph

    shapes = Graph()
    shapes.parse(data=META_SHAPE_TTL, format="turtle")

    conforms, results_graph, _ = pyshacl.validate(
        graph, shacl_graph=shapes, inference="none", abort_on_first=False
    )
    if conforms:
        return True, [], graph

    SH = Namespace("http://www.w3.org/ns/shacl#")
    violations = [
        str(msg)
        for node in results_graph.subjects(RDF.type, SH.ValidationResult)
        for msg in results_graph.objects(node, SH.resultMessage)
    ]
    return False, violations or ["meta-model validation failed"], graph


class MetaModelRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._graph = Graph()
        self._properties: dict[str, PropertyDefinition] = {}
        self._subsystems: dict[str, dict[str, str]] = {}
        self._history: list[LoadResult] = []
        self._version = self._compute_version()

    def _compute_version(self) -> str:
        with_lock = self._graph.serialize(format="nt")
        canonical = "\n".join(sorted(with_lock.splitlines()))
        return hashlib.sha256(canonical.encode()).hexdigest()[:12]

    @property
    def version(self) -> str:
        with self._lock:
            return self._version

    def reset(self) -> None:
        with self._lock:
            self._graph = Graph()
            self._properties.clear()
            self._subsystems.clear()
            self._history.clear()
            self._version = self._compute_version()

    def load_turtle(self, turtle: str) -> LoadResult:
        accepted, violations, fragment = validate_fragment(turtle)
        now = datetime.now(timezone.utc).isoformat()

        if not accepted:
            result = LoadResult(
                accepted=False,
                version=self.version,
                triples_added=0,
                violations=violations,
                loaded_at=now,
            )
            with self._lock:
                self._history.insert(0, result)
            return result

        with self._lock:
            before = len(self._graph)
            self._graph += fragment
            added = len(self._graph) - before

            new_subsystems = []
            for subject in fragment.subjects(RDF.type, SF.Subsystem):
                key = _local_name(subject)
                if key in self._subsystems:
                    continue
                labels = {
                    (lit.language or "en"): str(lit)
                    for lit in fragment.objects(subject, RDFS.label)
                }
                self._subsystems[key] = {"uri": str(subject), "labels": labels}
                new_subsystems.append(key)

            new_properties = []
            for subject in fragment.subjects(RDF.type, SOSA.ObservableProperty):
                name = _local_name(subject)
                labels = {
                    (lit.language or "en"): str(lit)
                    for lit in fragment.objects(subject, RDFS.label)
                }
                subsystem = fragment.value(subject, SF.belongsToSubsystem)
                definition = PropertyDefinition(
                    uri=str(subject),
                    name=name,
                    labels=labels,
                    unit=str(fragment.value(subject, SF.hasUnit) or ""),
                    min_value=_float_or_none(fragment, subject, SF.minValue) or 0.0,
                    max_value=_float_or_none(fragment, subject, SF.maxValue) or 0.0,
                    subsystem=_local_name(subsystem) if subsystem else "",
                    warn_threshold=_float_or_none(fragment, subject, SF.warnThreshold),
                    danger_threshold=_float_or_none(
                        fragment, subject, SF.dangerThreshold
                    ),
                    direction=str(fragment.value(subject, SF.direction) or "high"),
                )
                self._properties[name] = definition
                new_properties.append(name)

            self._version = self._compute_version()
            result = LoadResult(
                accepted=True,
                version=self._version,
                triples_added=added,
                properties_added=new_properties,
                subsystems_added=new_subsystems,
                loaded_at=now,
            )
            self._history.insert(0, result)
            del self._history[50:]

        logger.info(
            "meta-model extended: +%d triples, properties=%s, version=%s",
            added,
            new_properties,
            self._version,
        )
        return result

    def properties(self) -> dict[str, PropertyDefinition]:
        with self._lock:
            return dict(self._properties)

    def get(self, name: str) -> Optional[PropertyDefinition]:
        with self._lock:
            return self._properties.get(name)

    def knows(self, name: str) -> bool:
        with self._lock:
            return name in self._properties

    def subsystems(self) -> dict[str, dict[str, str]]:
        with self._lock:
            return dict(self._subsystems)

    def hard_limits(self) -> dict[str, tuple[float, float]]:
        with self._lock:
            return {
                name: (d.min_value, d.max_value) for name, d in self._properties.items()
            }

    def thresholds(self) -> dict[str, tuple[float, str]]:
        with self._lock:
            out = {}
            for name, d in self._properties.items():
                if d.danger_threshold is not None:
                    out[name] = (d.danger_threshold, d.direction)
            return out

    def dashboard_fields(self) -> list[dict[str, Any]]:
        with self._lock:
            fields = []
            for name, d in self._properties.items():
                fields.append(
                    {
                        "key": name,
                        "label": d.labels.get("zh") or d.labels.get("en") or name,
                        "unit": d.unit.rsplit("/", 1)[-1],
                        "min": d.min_value,
                        "max": d.max_value,
                        "warn": d.warn_threshold,
                        "danger": d.danger_threshold,
                        "direction": d.direction,
                        "subsystem": d.subsystem,
                    }
                )
            fields.sort(key=lambda f: f["key"])
            return fields

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            return [r.to_dict() for r in self._history[:limit]]

    def serialize(self, fmt: str = "turtle") -> str:
        with self._lock:
            return self._graph.serialize(format=fmt)


registry = MetaModelRegistry()
