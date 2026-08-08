# Tests for shacl_runner.py

from datetime import datetime, timezone

from rdflib import RDF, XSD, Graph, Literal, SOSA, URIRef

from semantic_layer.mapping import to_rdf_graph
from semantic_layer.shacl_runner import ValidationReport, validate, _fallback_validate
from smart_factory_contracts.messages import (
    Measurement, MeasurementType, Protocol, Subsystem, UnifiedMessage, Unit,
)

SF = "http://example.org/smart-factory#"


def _msg(**overrides):
    defaults = dict(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        timestamp=datetime(2026, 7, 10, 9, 0, 0, tzinfo=timezone.utc),
        measurements=[
            Measurement(type=MeasurementType.TEMPERATURE, value=24.3, unit=Unit.CELSIUS),
        ],
    )
    defaults.update(overrides)
    return UnifiedMessage(**defaults)


# valid graphs

def test_valid_observation_passes():
    g = to_rdf_graph(_msg())
    result = validate(g)
    assert result.conforms is True
    assert result.violations == []


def test_valid_multi_measurement():
    msg = _msg(measurements=[
        Measurement(type=MeasurementType.TEMPERATURE, value=24.3, unit=Unit.CELSIUS),
        Measurement(type=MeasurementType.HUMIDITY, value=58.0, unit=Unit.PERCENT),
    ])
    g = to_rdf_graph(msg)
    result = validate(g)
    assert result.conforms


def test_gas_subsystem_valid():
    msg = _msg(
        device_id="sensor_mq2_01",
        subsystem=Subsystem.GAS,
        protocol=Protocol.MODBUS,
        measurements=[
            Measurement(type=MeasurementType.CO, value=12.0, unit=Unit.PPM),
            Measurement(type=MeasurementType.SMOKE, value=4.0, unit=Unit.PPM),
            Measurement(type=MeasurementType.COMBUSTIBLE_GAS, value=1.5, unit=Unit.PPM),
        ],
    )
    g = to_rdf_graph(msg)
    result = validate(g)
    assert result.conforms, result.violations


# invalid graphs

def _empty_obs():
    g = Graph()
    obs = URIRef(f"{SF}obs_bad_01")
    g.add((obs, RDF.type, SOSA.Observation))
    return g


def test_empty_observation_fails():
    g = _empty_obs()
    result = validate(g)
    assert result.conforms is False
    assert len(result.violations) > 0


def test_missing_sensor_detected():
    g = Graph()
    obs = URIRef(f"{SF}obs_no_sensor")
    g.add((obs, RDF.type, SOSA.Observation))
    g.add((obs, SOSA.observedProperty, URIRef(f"{SF}measuresTemperature")))
    g.add((obs, SOSA.hasSimpleResult, Literal(25.0, datatype=XSD.double)))
    g.add((obs, SOSA.resultTime, Literal("2026-07-10T09:00:00+00:00", datatype=XSD.dateTime)))

    result = validate(g)
    assert not result.conforms
    # should mention the missing sensor somewhere
    combined = " ".join(result.violations).lower()
    assert "sensor" in combined or "madebysensor" in combined.replace(" ", "")


def test_no_observations_fails():
    g = Graph()
    result = validate(g)
    assert not result.conforms


# summary string

def test_summary_valid():
    g = to_rdf_graph(_msg())
    result = validate(g)
    assert "✓" in result.summary()


def test_summary_invalid():
    result = validate(Graph())
    assert "✗" in result.summary()


# fallback path specifically

def test_fallback_valid():
    g = to_rdf_graph(_msg())
    result = _fallback_validate(g)
    assert isinstance(result, ValidationReport)
    assert result.conforms is True


def test_fallback_catches_missing_property():
    g = Graph()
    obs = URIRef(f"{SF}obs_test")
    g.add((obs, RDF.type, SOSA.Observation))
    g.add((obs, SOSA.madeBySensor, URIRef(f"{SF}sensor_test")))
    # deliberately skip observedProperty
    g.add((obs, SOSA.hasSimpleResult, Literal(10.0, datatype=XSD.double)))
    g.add((obs, SOSA.resultTime, Literal("2026-07-10T09:00:00+00:00", datatype=XSD.dateTime)))

    result = _fallback_validate(g)
    assert not result.conforms
    assert any("observedProperty" in v for v in result.violations)
