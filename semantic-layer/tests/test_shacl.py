# Tests for shacl_validator.py — verifies that the validator correctly
# accepts well-formed SOSA observations and catches malformed ones.

from datetime import datetime, timezone

from rdflib import RDF, XSD, Graph, Literal, SOSA, URIRef

from semantic_layer.mapping import to_rdf_graph
from semantic_layer.shacl_validator import validate_and_explain, validate_observation_graph
from smart_factory_contracts.messages import (
    Measurement,
    MeasurementType,
    Protocol,
    Subsystem,
    UnifiedMessage,
    Unit,
)

SF = "http://example.org/smart-factory#"

# Helper
def _make_msg(**overrides):
    defaults = dict(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        timestamp=datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc),
        measurements=[
            Measurement(type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS)
        ],
    )
    defaults.update(overrides)
    return UnifiedMessage(**defaults)

# Happy-path tests

def test_valid_single_measurement_passes():
    g = to_rdf_graph(_make_msg())
    ok, errors = validate_observation_graph(g)
    assert ok, f"Expected valid but got: {errors}"
    assert errors == []


def test_valid_multi_measurement_passes():
    msg = _make_msg(
        measurements=[
            Measurement(type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS),
            Measurement(type=MeasurementType.HUMIDITY,    value=62.0, unit=Unit.PERCENT),
        ]
    )
    g = to_rdf_graph(msg)
    ok, errors = validate_observation_graph(g)
    assert ok, errors


def test_valid_gas_message_passes():
    msg = _make_msg(
        device_id="sensor_mq2_01",
        subsystem=Subsystem.GAS,
        protocol=Protocol.MODBUS,
        measurements=[
            Measurement(type=MeasurementType.CO,    value=10.0, unit=Unit.PPM),
            Measurement(type=MeasurementType.SMOKE, value=3.0,  unit=Unit.PPM),
        ],
    )
    g = to_rdf_graph(msg)
    ok, errors = validate_observation_graph(g)
    assert ok, errors

# Failure tests

def _bare_observation() -> tuple[Graph, URIRef]:
    """Return an empty graph and a fresh Observation URI (no predicates yet)."""
    g = Graph()
    obs = URIRef(f"{SF}obs_test_bad")
    g.add((obs, RDF.type, SOSA.Observation))
    return g, obs


def test_missing_made_by_sensor_fails():
    g, obs = _bare_observation()
    # Add everything EXCEPT madeBySensor
    g.add((obs, SOSA.observedProperty, URIRef(f"{SF}measuresTemperature")))
    g.add((obs, SOSA.hasSimpleResult,  Literal(25.5, datatype=XSD.double)))
    g.add((obs, SOSA.resultTime,       Literal("2026-07-01T12:00:00+00:00", datatype=XSD.dateTime)))

    ok, errors = validate_observation_graph(g)
    assert not ok
    assert any("madeBySensor" in e for e in errors)


def test_missing_observed_property_fails():
    g, obs = _bare_observation()
    g.add((obs, SOSA.madeBySensor,    URIRef(f"{SF}sensor_dht22_01")))
    g.add((obs, SOSA.hasSimpleResult, Literal(25.5, datatype=XSD.double)))
    g.add((obs, SOSA.resultTime,      Literal("2026-07-01T12:00:00+00:00", datatype=XSD.dateTime)))

    ok, errors = validate_observation_graph(g)
    assert not ok
    assert any("observedProperty" in e for e in errors)


def test_missing_simple_result_fails():
    g, obs = _bare_observation()
    g.add((obs, SOSA.madeBySensor,    URIRef(f"{SF}sensor_dht22_01")))
    g.add((obs, SOSA.observedProperty, URIRef(f"{SF}measuresTemperature")))
    g.add((obs, SOSA.resultTime,       Literal("2026-07-01T12:00:00+00:00", datatype=XSD.dateTime)))

    ok, errors = validate_observation_graph(g)
    assert not ok
    assert any("hasSimpleResult" in e for e in errors)


def test_missing_result_time_fails():
    g, obs = _bare_observation()
    g.add((obs, SOSA.madeBySensor,     URIRef(f"{SF}sensor_dht22_01")))
    g.add((obs, SOSA.observedProperty, URIRef(f"{SF}measuresTemperature")))
    g.add((obs, SOSA.hasSimpleResult,  Literal(25.5, datatype=XSD.double)))

    ok, errors = validate_observation_graph(g)
    assert not ok
    assert any("resultTime" in e for e in errors)


def test_empty_graph_fails_with_no_observations():
    ok, errors = validate_observation_graph(Graph())
    assert not ok
    assert len(errors) == 1
    assert "zero" in errors[0].lower() or "no" in errors[0].lower() or "Observation" in errors[0]

# validate_and_explain() convenience wrapper

def test_explain_valid_starts_with_checkmark():
    g = to_rdf_graph(_make_msg())
    report = validate_and_explain(g)
    assert report.startswith("✓"), f"Expected ✓ but got: {report}"


def test_explain_invalid_starts_with_cross():
    report = validate_and_explain(Graph())
    assert report.startswith("✗"), f"Expected ✗ but got: {report}"


def test_explain_valid_mentions_observation_count():
    msg = _make_msg(
        measurements=[
            Measurement(type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS),
            Measurement(type=MeasurementType.HUMIDITY,    value=60.0, unit=Unit.PERCENT),
        ]
    )
    g = to_rdf_graph(msg)
    report = validate_and_explain(g)
    assert "2" in report
