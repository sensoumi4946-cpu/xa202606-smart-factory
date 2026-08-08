# Tests for provenance.py 

from datetime import datetime, timezone

from rdflib import RDF, SOSA, Graph, Namespace

from semantic_layer.mapping import to_rdf_graph
from semantic_layer.provenance import PROV, SF, build_activity, stamp_provenance
from smart_factory_contracts.messages import (
    Measurement, MeasurementType, Protocol, Subsystem, UnifiedMessage, Unit,
)


def _msg(**kw):
    defaults = dict(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        timestamp=datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc),
        measurements=[
            Measurement(type=MeasurementType.TEMPERATURE, value=23.0, unit=Unit.CELSIUS),
        ],
    )
    defaults.update(kw)
    return UnifiedMessage(**defaults)


def _make_graph(**kw):
    return to_rdf_graph(_msg(**kw))


# stamp_provenance

def test_stamp_adds_agent():
    g = _make_graph()
    stamp_provenance(g, protocol="mqtt", device_id="sensor_dht22_01")
    agents = list(g.subjects(RDF.type, PROV.SoftwareAgent))
    assert len(agents) == 1
    assert "adapter_mqtt" in str(agents[0])


def test_stamp_adds_generated_time():
    g = _make_graph()
    stamp_provenance(g, protocol="mqtt", device_id="sensor_dht22_01")
    times = list(g.objects(None, PROV.generatedAtTime))
    assert len(times) >= 1


def test_stamp_links_observations_to_agent():
    g = _make_graph()
    stamp_provenance(g, protocol="mqtt", device_id="sensor_dht22_01")
    # every observation should have wasAttributedTo
    for obs in g.subjects(RDF.type, SOSA.Observation):
        attrs = list(g.objects(obs, PROV.wasAttributedTo))
        assert len(attrs) == 1


def test_stamp_custom_time():
    g = _make_graph()
    custom_time = datetime(2026, 7, 10, 15, 0, 0, tzinfo=timezone.utc)
    stamp_provenance(g, "mqtt", "sensor_dht22_01", ingested_at=custom_time)
    times = [str(t) for t in g.objects(None, PROV.generatedAtTime)]
    assert any("2026-07-10T15:00:00" in t for t in times)


def test_stamp_modbus_protocol():
    g = _make_graph(
        device_id="sensor_mq2_01",
        subsystem=Subsystem.GAS,
        protocol=Protocol.MODBUS,
        measurements=[
            Measurement(type=MeasurementType.CO, value=10.0, unit=Unit.PPM),
        ],
    )
    stamp_provenance(g, "modbus", "sensor_mq2_01")
    agents = list(g.subjects(RDF.type, PROV.SoftwareAgent))
    assert any("adapter_modbus" in str(a) for a in agents)


def test_stamp_returns_graph():
    g = _make_graph()
    result = stamp_provenance(g, "mqtt", "sensor_dht22_01")
    assert result is g


def test_agent_has_protocol_literal():
    g = _make_graph()
    stamp_provenance(g, "mqtt", "sensor_dht22_01")
    protocols = list(g.objects(None, SF.protocol))
    assert any(str(p) == "mqtt" for p in protocols)


# build_activity

def test_build_activity_creates_node():
    g = Graph()
    started = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
    uri = build_activity(g, "batch_001", started, label="test ingest")
    assert (uri, RDF.type, PROV.Activity) in g


def test_build_activity_has_start_time():
    g = Graph()
    started = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
    uri = build_activity(g, "batch_002", started)
    times = list(g.objects(uri, PROV.startedAtTime))
    assert len(times) == 1


def test_build_activity_end_time_optional():
    g = Graph()
    started = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
    uri = build_activity(g, "batch_003", started)
    ends = list(g.objects(uri, PROV.endedAtTime))
    assert len(ends) == 0


def test_build_activity_with_end_time():
    g = Graph()
    started = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
    ended = datetime(2026, 7, 10, 12, 5, 0, tzinfo=timezone.utc)
    uri = build_activity(g, "batch_004", started, ended=ended)
    ends = list(g.objects(uri, PROV.endedAtTime))
    assert len(ends) == 1
