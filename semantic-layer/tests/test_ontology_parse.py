from importlib.resources import files

from rdflib import RDFS, Graph, SOSA
from rdflib.term import URIRef

ONTOLOGY_PATH = files("semantic_layer") / "ontology" / "smart-factory.ttl"
SF = "http://example.org/smart-factory#"


def _load_graph() -> Graph:
    g = Graph()
    with open(ONTOLOGY_PATH, "rb") as f:
        g.parse(f, format="turtle")
    return g


def test_ontology_parseable():
    g = _load_graph()
    assert len(g) > 0


def test_sensor_classes_present():
    g = _load_graph()
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
    g = _load_graph()
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
    g = _load_graph()
    temp_sensor = URIRef(f"{SF}TemperatureSensor")
    results = list(g.triples((temp_sensor, RDFS.subClassOf, SOSA.Sensor)))
    assert len(results) > 0


def test_subsystems_present():
    g = _load_graph()
    subsystems = [
        URIRef(f"{SF}TempHumiditySubsystem"),
        URIRef(f"{SF}LightingSubsystem"),
        URIRef(f"{SF}GasMonitoringSubsystem"),
        URIRef(f"{SF}AGVObstacleSubsystem"),
        URIRef(f"{SF}CountingSubsystem"),
    ]
    for sub in subsystems:
        assert (sub, None, None) in g, f"{sub} not found in ontology"
