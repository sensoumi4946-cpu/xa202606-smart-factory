from pathlib import Path

from rdflib import RDFS, Graph, OWL, SOSA
from rdflib.term import URIRef

ONTOLOGY_PATH = Path(__file__).parent.parent / "ontology" / "smart-factory.ttl"
SF = "http://example.org/smart-factory#"


def test_ontology_parseable():
    g = Graph()
    g.parse(str(ONTOLOGY_PATH), format="turtle")
    assert len(g) > 0


def test_sensor_classes_present():
    g = Graph()
    g.parse(str(ONTOLOGY_PATH), format="turtle")
    sensor_classes = [
        URIRef(f"{SF}TemperatureSensor"),
        URIRef(f"{SF}HumiditySensor"),
        URIRef(f"{SF}GasSensor"),
        URIRef(f"{SF}ProximitySensor"),
        URIRef(f"{SF}CountSensor"),
        URIRef(f"{SF}OccupancySensor"),
    ]
    for cls in sensor_classes:
        assert (cls, None, None) in g, f"{cls} not found in ontology"


def test_observable_properties_present():
    g = Graph()
    g.parse(str(ONTOLOGY_PATH), format="turtle")
    props = [
        URIRef(f"{SF}measuresTemperature"),
        URIRef(f"{SF}measuresHumidity"),
        URIRef(f"{SF}measuresCO"),
        URIRef(f"{SF}measuresSmoke"),
        URIRef(f"{SF}measuresCombustibleGas"),
        URIRef(f"{SF}measuresDistance"),
        URIRef(f"{SF}measuresCount"),
        URIRef(f"{SF}measuresOccupancy"),
        URIRef(f"{SF}measuresLightState"),
    ]
    for prop in props:
        assert (prop, None, None) in g, f"{prop} not found in ontology"


def test_sensor_uses_sosa_sensor():
    g = Graph()
    g.parse(str(ONTOLOGY_PATH), format="turtle")
    temp_sensor = URIRef(f"{SF}TemperatureSensor")
    results = list(g.triples((temp_sensor, RDFS.subClassOf, SOSA.Sensor)))
    assert len(results) > 0


def test_subsystems_present():
    g = Graph()
    g.parse(str(ONTOLOGY_PATH), format="turtle")
    subsystems = [
        URIRef(f"{SF}TempHumiditySubsystem"),
        URIRef(f"{SF}LightingSubsystem"),
        URIRef(f"{SF}GasMonitoringSubsystem"),
        URIRef(f"{SF}AGVObstacleSubsystem"),
        URIRef(f"{SF}CountingSubsystem"),
    ]
    for sub in subsystems:
        assert (sub, None, None) in g, f"{sub} not found in ontology"
