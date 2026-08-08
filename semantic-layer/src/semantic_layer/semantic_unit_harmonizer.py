# Defines a QUDT-aligned unit registry (URIs + conversion fns)

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from rdflib import RDF, XSD, Graph, Literal, Namespace, URIRef
from rdflib.namespace import SOSA

QUDT = Namespace("http://qudt.org/schema/qudt/")
UNIT = Namespace("http://qudt.org/vocab/unit/")
SF   = Namespace("http://example.org/smart-factory#")

# Unit registry

@dataclass(frozen=True)
class UnitDescriptor:
    raw_label: str         
    qudt_uri: URIRef        
    si_uri: URIRef          
    to_si: Callable[[float], float]  
    si_label: str           
    quantity_kind: URIRef


# All five subsystems' units, plus the ones the analytics layer references
_REGISTRY: list[UnitDescriptor] = [
    UnitDescriptor(
        raw_label="celsius",
        qudt_uri=UNIT["DEG_C"],
        si_uri=UNIT["K"],
        to_si=lambda v: v + 273.15,
        si_label="kelvin",
        quantity_kind=URIRef("http://qudt.org/vocab/quantitykind/Temperature"),
    ),
    UnitDescriptor(
        raw_label="fahrenheit",
        qudt_uri=UNIT["DEG_F"],
        si_uri=UNIT["K"],
        to_si=lambda v: (v - 32) * 5 / 9 + 273.15,
        si_label="kelvin",
        quantity_kind=URIRef("http://qudt.org/vocab/quantitykind/Temperature"),
    ),
    UnitDescriptor(
        raw_label="kelvin",
        qudt_uri=UNIT["K"],
        si_uri=UNIT["K"],
        to_si=lambda v: v,
        si_label="kelvin",
        quantity_kind=URIRef("http://qudt.org/vocab/quantitykind/Temperature"),
    ),
    UnitDescriptor(
        raw_label="ppm",
        qudt_uri=UNIT["PPM"],
        si_uri=UNIT["PPM"],
        to_si=lambda v: v,
        si_label="parts per million",
        quantity_kind=URIRef("http://qudt.org/vocab/quantitykind/Concentration"),
    ),
    UnitDescriptor(
        raw_label="percent",
        qudt_uri=UNIT["PERCENT"],
        si_uri=UNIT["PERCENT"],
        to_si=lambda v: v,
        si_label="percent",
        quantity_kind=URIRef("http://qudt.org/vocab/quantitykind/DimensionlessRatio"),
    ),
    UnitDescriptor(
        raw_label="cm",
        qudt_uri=UNIT["CentiM"],
        si_uri=UNIT["M"],
        to_si=lambda v: v / 100.0,
        si_label="meter",
        quantity_kind=URIRef("http://qudt.org/vocab/quantitykind/Length"),
    ),
    UnitDescriptor(
        raw_label="mm",
        qudt_uri=UNIT["MilliM"],
        si_uri=UNIT["M"],
        to_si=lambda v: v / 1000.0,
        si_label="meter",
        quantity_kind=URIRef("http://qudt.org/vocab/quantitykind/Length"),
    ),
    UnitDescriptor(
        raw_label="count",
        qudt_uri=UNIT["NUM"],
        si_uri=UNIT["NUM"],
        to_si=lambda v: v,
        si_label="count",
        quantity_kind=URIRef("http://qudt.org/vocab/quantitykind/Dimensionless"),
    ),
    UnitDescriptor(
        raw_label="boolean",
        qudt_uri=UNIT["NUM"],
        si_uri=UNIT["NUM"],
        to_si=lambda v: float(bool(v)),
        si_label="boolean (0/1)",
        quantity_kind=URIRef("http://qudt.org/vocab/quantitykind/Dimensionless"),
    ),
]

_BY_LABEL: dict[str, UnitDescriptor] = {d.raw_label: d for d in _REGISTRY}


# Public API

def resolve(raw_label: str) -> Optional[UnitDescriptor]:
    return _BY_LABEL.get(raw_label.lower())


def harmonize_to_si(raw_label: str, value: float) -> Optional[tuple[float, URIRef, str]]:
    desc = resolve(raw_label)
    if desc is None:
        return None
    return desc.to_si(value), desc.si_uri, desc.si_label


def enrich_graph_with_qudt(g: Graph) -> Graph:
    g.bind("qudt", QUDT)
    g.bind("unit", UNIT)

    has_unit = SF.hasUnit
    unit_failed = SF.unitHarmonizationFailed

    for obs in list(g.subjects(RDF.type, SOSA.Observation)):
        unit_literals = list(g.objects(obs, has_unit))
        result_literals = list(g.objects(obs, SOSA.hasSimpleResult))

        if not unit_literals or not result_literals:
            continue

        raw_unit = str(unit_literals[0]).lower()
        raw_value = float(result_literals[0])

        desc = resolve(raw_unit)
        if desc is None:
            g.add((obs, unit_failed, Literal(raw_unit)))
            continue

        g.add((obs, QUDT.unit, desc.qudt_uri))

        si_val = desc.to_si(raw_value)
        g.add((obs, QUDT.value, Literal(round(si_val, 6), datatype=XSD.double)))
        g.add((obs, QUDT.hasQuantityKind, desc.quantity_kind))

    return g