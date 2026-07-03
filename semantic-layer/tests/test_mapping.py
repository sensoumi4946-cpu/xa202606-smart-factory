# Tests for semantic mapping (UnifiedMessage → RDF triples).
#
# Each test constructs a UnifiedMessage, calls to_rdf_graph(), and
# asserts the resulting RDFlib Graph contains the expected triples.
# SPARQL queries are executed locally — no external Fuseki/AAS runtime.
from datetime import datetime, timezone

from rdflib import RDF, Graph, SOSA
from rdflib.term import URIRef
from smart_factory_contracts.messages import (
    Measurement,
    MeasurementType,
    Protocol,
    Subsystem,
    UnifiedMessage,
    Unit,
)

from semantic_layer.mapping import (
    TYPE_TO_PROPERTY,
    TYPE_TO_SENSOR_CLASS,
    to_rdf_graph,
)

SF = "http://example.org/smart-factory#"


def _make_msg(**kwargs):
    defaults = {
        "schema_version": "v1",
        "device_id": "sensor_dht22_01",
        "subsystem": Subsystem.TEMP_HUMIDITY,
        "protocol": Protocol.MQTT,
        "timestamp": datetime(2026, 7, 15, 10, 30, 0, tzinfo=timezone.utc),
        "measurements": [
            Measurement(
                type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS
            ),
        ],
    }
    defaults.update(kwargs)
    return UnifiedMessage(**defaults)


def test_map_temperature_creates_observation():
    msg = _make_msg()
    g = to_rdf_graph(msg)
    assert (None, RDF.type, SOSA.Observation) in g

    prop_uri = TYPE_TO_PROPERTY[MeasurementType.TEMPERATURE]
    assert (None, SOSA.observedProperty, prop_uri) in g

    device_uri = URIRef(f"{SF}{msg.device_id}")
    assert (None, SOSA.madeBySensor, device_uri) in g


def test_observation_has_result_time():
    msg = _make_msg()
    g = to_rdf_graph(msg)
    assert (None, SOSA.resultTime, None) in g
    timestamps = list(g.objects(None, SOSA.resultTime))
    assert len(timestamps) >= 1


def test_unit_subsystem_protocol_preserved():
    msg = _make_msg(
        measurements=[
            Measurement(
                type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS
            ),
        ],
    )
    g = to_rdf_graph(msg)

    has_unit = URIRef(f"{SF}hasUnit")
    belongs = URIRef(f"{SF}belongsToSubsystem")
    via = URIRef(f"{SF}transportedVia")

    assert (None, has_unit, None) in g
    assert (None, belongs, None) in g
    assert (None, via, None) in g

    units = list(g.objects(None, has_unit))
    assert "celsius" in [str(u) for u in units]


def test_all_measurement_types_mapped():
    for mtype in MeasurementType:
        msg = _make_msg(
            device_id=f"sensor_test_{mtype.value}",
            measurements=[Measurement(type=mtype, value=1.0, unit=Unit.COUNT)],
        )
        g = to_rdf_graph(msg)
        assert len(g) > 0
        assert (None, RDF.type, SOSA.Observation) in g

        prop = TYPE_TO_PROPERTY.get(mtype)
        assert prop is not None
        assert (None, SOSA.observedProperty, prop) in g

        if mtype == MeasurementType.LIGHT_STATE:
            assert mtype not in TYPE_TO_SENSOR_CLASS
        else:
            assert mtype in TYPE_TO_SENSOR_CLASS


def test_multiple_measurements_produce_multiple_observations():
    msg = _make_msg(
        measurements=[
            Measurement(
                type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS
            ),
            Measurement(type=MeasurementType.HUMIDITY, value=62.1, unit=Unit.PERCENT),
        ],
    )
    g = to_rdf_graph(msg)
    obs = list(g.subjects(RDF.type, SOSA.Observation))
    assert len(obs) == 2


def test_sparql_find_co_and_temp_sensors():
    g = Graph()
    for dev_id, subsys, mlist in [
        (
            "sensor_dht22_01",
            Subsystem.TEMP_HUMIDITY,
            [
                Measurement(
                    type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS
                ),
            ],
        ),
        (
            "sensor_mq2_01",
            Subsystem.GAS,
            [
                Measurement(type=MeasurementType.CO, value=5.0, unit=Unit.PPM),
            ],
        ),
        (
            "sensor_ir_01",
            Subsystem.COUNTING,
            [
                Measurement(type=MeasurementType.COUNT, value=10.0, unit=Unit.COUNT),
            ],
        ),
    ]:
        msg = _make_msg(device_id=dev_id, subsystem=subsys, measurements=mlist)
        g += to_rdf_graph(msg)

    query = """
        SELECT DISTINCT ?sensor WHERE {
            ?obs a sosa:Observation ;
                 sosa:observedProperty ?prop ;
                 sosa:madeBySensor ?sensor .
            VALUES ?prop { sf:measuresTemperature sf:measuresCO }
        }
    """
    ns = {"sosa": str(SOSA), "sf": SF}
    results = g.query(query, initNs=ns)
    sensors = {str(row.sensor) for row in results}
    assert f"{SF}sensor_dht22_01" in sensors
    assert f"{SF}sensor_mq2_01" in sensors
    assert f"{SF}sensor_ir_01" not in sensors
