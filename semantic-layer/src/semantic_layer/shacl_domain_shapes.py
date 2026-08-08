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

sf:TemperatureBranch
    a sh:NodeShape ;
    sh:property [
        sh:path sosa:observedProperty ;
        sh:hasValue sf:measuresTemperature ;
    ] ;
    sh:property [
        sh:path sosa:hasSimpleResult ;
        sh:minInclusive -60.0 ;
        sh:maxInclusive 150.0 ;
        sh:message "Temperature value must be in range [-60, 150] C." ;
        sh:severity sh:Violation ;
    ] ;
    sh:property [
        sh:path sf:hasUnit ;
        sh:in ( "celsius" "fahrenheit" "kelvin" ) ;
        sh:message "Temperature unit must be 'celsius', 'fahrenheit', or 'kelvin'." ;
        sh:severity sh:Violation ;
    ] .

sf:HumidityBranch
    a sh:NodeShape ;
    sh:property [
        sh:path sosa:observedProperty ;
        sh:hasValue sf:measuresHumidity ;
    ] ;
    sh:property [
        sh:path sosa:hasSimpleResult ;
        sh:minInclusive 0.0 ;
        sh:maxInclusive 100.0 ;
        sh:message "Humidity must be in range [0, 100] percent." ;
        sh:severity sh:Violation ;
    ] ;
    sh:property [
        sh:path sf:hasUnit ;
        sh:in ( "percent" ) ;
        sh:message "Humidity unit must be 'percent'." ;
        sh:severity sh:Violation ;
    ] .

sf:GasBranch
    a sh:NodeShape ;
    sh:property [
        sh:path sosa:observedProperty ;
        sh:in ( sf:measuresCO sf:measuresSmoke sf:measuresCombustibleGas ) ;
    ] ;
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

sf:DistanceBranch
    a sh:NodeShape ;
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

sf:CountBranch
    a sh:NodeShape ;
    sh:property [
        sh:path sosa:observedProperty ;
        sh:hasValue sf:measuresCount ;
    ] ;
    sh:property [
        sh:path sosa:hasSimpleResult ;
        sh:minInclusive 0.0 ;
        sh:maxInclusive 100000.0 ;
        sh:message "Count value must be zero or a positive number." ;
        sh:severity sh:Violation ;
    ] ;
    sh:property [
        sh:path sf:hasUnit ;
        sh:in ( "count" ) ;
        sh:message "Count unit must be 'count'." ;
        sh:severity sh:Violation ;
    ] .

sf:OccupancyBranch
    a sh:NodeShape ;
    sh:property [
        sh:path sosa:observedProperty ;
        sh:hasValue sf:measuresOccupancy ;
    ] ;
    sh:property [
        sh:path sosa:hasSimpleResult ;
        sh:in ( "0.0"^^xsd:double "1.0"^^xsd:double ) ;
        sh:message "Occupancy value must be 0 or 1." ;
        sh:severity sh:Violation ;
    ] ;
    sh:property [
        sh:path sf:hasUnit ;
        sh:in ( "boolean" ) ;
        sh:message "Occupancy unit must be 'boolean'." ;
        sh:severity sh:Violation ;
    ] .

sf:LightStateBranch
    a sh:NodeShape ;
    sh:property [
        sh:path sosa:observedProperty ;
        sh:hasValue sf:measuresLightState ;
    ] ;
    sh:property [
        sh:path sosa:hasSimpleResult ;
        sh:in ( "0.0"^^xsd:double "1.0"^^xsd:double ) ;
        sh:message "Light state value must be 0 or 1." ;
        sh:severity sh:Violation ;
    ] ;
    sh:property [
        sh:path sf:hasUnit ;
        sh:in ( "boolean" ) ;
        sh:message "Light state unit must be 'boolean'." ;
        sh:severity sh:Violation ;
    ] .

# ── Dispatcher: every Observation must satisfy exactly one branch above ──

sf:ObservationDomainShape
    a sh:NodeShape ;
    sh:targetClass sosa:Observation ;
    rdfs:comment "Routes each observation to the ONE branch matching its measured property, instead of forcing it to satisfy all branches." ;
    sh:or (
        sf:TemperatureBranch
        sf:HumidityBranch
        sf:GasBranch
        sf:DistanceBranch
        sf:CountBranch
        sf:OccupancyBranch
        sf:LightStateBranch
    ) ;
    sh:message "Observation does not satisfy the domain constraints for any known measurement type." ;
    sh:severity sh:Violation .

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

# QUDT enrichment presence check (Warning — only if harmonizer ran)

sf:QUDTEnrichmentShape
    a sh:NodeShape ;
    sh:targetClass sosa:Observation ;
    rdfs:comment "Warn if the unit harmonizer has not added qudt:unit." ;

    sh:property [
        sh:path qudt:unit ;
        sh:minCount 1 ;
        sh:message "Observation is missing qudt:unit triple - run semantic_unit_harmonizer.enrich_graph_with_qudt()." ;
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