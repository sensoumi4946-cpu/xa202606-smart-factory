"""

SHACL as semantic interoperability enforcement layer.

"""

DOMAIN_SHAPES_TTL = """\
@prefix sh:    <http://www.w3.org/ns/shacl#> .
@prefix sosa:  <http://www.w3.org/ns/sosa/> .
@prefix sf:    <http://example.org/smart-factory#> .
@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .
@prefix rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .
@prefix qudt:  <http://qudt.org/schema/qudt/> .

# Temperature observation: physical range + allowed units

sf:TemperatureObservationShape
    a sh:NodeShape ;
    sh:targetClass sosa:Observation ;
    rdfs:comment "Structural + domain constraint for temperature observations." ;

    # Only applies to observations of measuresTemperature
    sh:property [
        sh:path sosa:observedProperty ;
        sh:hasValue sf:measuresTemperature ;
    ] ;

    # Physical range: −60 °C to 150 °C
    sh:property [
        sh:path sosa:hasSimpleResult ;
        sh:minInclusive -60.0 ;
        sh:maxInclusive 150.0 ;
        sh:message "Temperature value must be in range [−60, 150] °C." ;
        sh:severity sh:Violation ;
    ] ;

    # Unit must be celsius, fahrenheit, or kelvin
    sh:property [
        sh:path sf:hasUnit ;
        sh:in ( "celsius" "fahrenheit" "kelvin" ) ;
        sh:message "Temperature unit must be 'celsius', 'fahrenheit', or 'kelvin'." ;
        sh:severity sh:Violation ;
    ] .

# Gas concentration: physical range + unit

sf:GasObservationShape
    a sh:NodeShape ;
    sh:targetClass sosa:Observation ;
    rdfs:comment "Domain constraint for gas sensor observations (CO, smoke, combustible gas)." ;

    sh:or (
        [ sh:property [ sh:path sosa:observedProperty ; sh:hasValue sf:measuresCO           ] ]
        [ sh:property [ sh:path sosa:observedProperty ; sh:hasValue sf:measuresSmoke         ] ]
        [ sh:property [ sh:path sosa:observedProperty ; sh:hasValue sf:measuresCombustibleGas] ]
    ) ;

    sh:property [
        sh:path sosa:hasSimpleResult ;
        sh:minInclusive 0.0 ;
        sh:maxInclusive 10000.0 ;
        sh:message "Gas concentration must be in range [0, 10000] ppm." ;
        sh:severity sh:Violation ;
    ] ;

    sh:property [
        sh:path sf:hasUnit ;
        sh:in ( "ppm" ) ;
        sh:message "Gas concentration unit must be 'ppm'." ;
        sh:severity sh:Violation ;
    ] .

# Humidity: range [0, 100] %, unit must be percent

sf:HumidityObservationShape
    a sh:NodeShape ;
    sh:targetClass sosa:Observation ;
    rdfs:comment "Domain constraint for humidity observations." ;

    sh:property [
        sh:path sosa:observedProperty ;
        sh:hasValue sf:measuresHumidity ;
    ] ;

    sh:property [
        sh:path sosa:hasSimpleResult ;
        sh:minInclusive 0.0 ;
        sh:maxInclusive 100.0 ;
        sh:message "Humidity must be in range [0, 100] %." ;
        sh:severity sh:Violation ;
    ] ;

    sh:property [
        sh:path sf:hasUnit ;
        sh:in ( "percent" ) ;
        sh:message "Humidity unit must be 'percent'." ;
        sh:severity sh:Violation ;
    ] .

# AGV distance: must be positive, unit cm

sf:DistanceObservationShape
    a sh:NodeShape ;
    sh:targetClass sosa:Observation ;

    sh:property [
        sh:path sosa:observedProperty ;
        sh:hasValue sf:measuresDistance ;
    ] ;

    sh:property [
        sh:path sosa:hasSimpleResult ;
        sh:minInclusive 0.0 ;
        sh:maxInclusive 2000.0 ;
        sh:message "AGV distance must be in range [0, 2000] cm." ;
        sh:severity sh:Violation ;
    ] ;

    sh:property [
        sh:path sf:hasUnit ;
        sh:in ( "cm" "mm" ) ;
        sh:message "Distance unit must be 'cm' or 'mm'." ;
        sh:severity sh:Violation ;
    ] .

# Subsystem membership: sensor must belong to a known subsystem (Warning)

sf:SensorSubsystemShape
    a sh:NodeShape ;
    sh:targetClass sosa:Sensor ;
    rdfs:comment "Warning if sensor has no subsystem assignment." ;

    sh:property [
        sh:path sf:belongsToSubsystem ;
        sh:minCount 1 ;
        sh:in (
            sf:TempHumiditySubsystem
            sf:LightingSubsystem
            sf:GasMonitoringSubsystem
            sf:AGVObstacleSubsystem
            sf:CountingSubsystem
        ) ;
        sh:message "Sensor should belong to one of the five known factory subsystems." ;
        sh:severity sh:Warning ;
    ] .

# 6.  QUDT enrichment presence check (Warning — only if harmonizer ran)

sf:QUDTEnrichmentShape
    a sh:NodeShape ;
    sh:targetClass sosa:Observation ;
    rdfs:comment "Warn if the unit harmonizer has not added qudt:unit." ;

    sh:property [
        sh:path qudt:unit ;
        sh:minCount 1 ;
        sh:message "Observation is missing qudt:unit triple — run semantic_unit_harmonizer.enrich_graph_with_qudt()." ;
        sh:severity sh:Warning ;
    ] .
"""


# Python loader

from pathlib import Path
from rdflib import Graph


def load_domain_shapes() -> Graph:
    g = Graph()
    g.parse(data=DOMAIN_SHAPES_TTL, format="turtle")
    return g


def load_all_shapes() -> Graph:
    structural_path = Path(__file__).resolve().parent / "shapes" / "observation_shapes.ttl"
    combined = Graph()
    if structural_path.exists():
        combined.parse(str(structural_path), format="turtle")
    combined += load_domain_shapes()
    return combined
