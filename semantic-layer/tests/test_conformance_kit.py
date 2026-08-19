import pytest

from semantic_layer.conformance_kit import (
    SEVERITY_BLOCKING,
    ConformanceCase,
    generate_cases,
    render,
    run_kit,
    to_json,
)
from semantic_layer.meta_model import MetaModelRegistry

TEMP_TTL = """
@prefix sf:   <http://example.org/smart-factory#> .
@prefix sosa: <http://www.w3.org/ns/sosa/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix unit: <http://qudt.org/vocab/unit/> .

sf:measuresTemperature a sosa:ObservableProperty ;
    rdfs:label "temperature"@en, "温度"@zh ;
    sf:hasUnit unit:DEG_C ;
    sf:minValue "-40.0"^^xsd:double ;
    sf:maxValue "80.0"^^xsd:double ;
    sf:belongsToSubsystem sf:TempHumiditySubsystem .

sf:TempHumiditySubsystem a sf:Subsystem ; rdfs:label "温湿度"@zh .
"""

VIBRATION_TTL = """
@prefix sf:   <http://example.org/smart-factory#> .
@prefix sosa: <http://www.w3.org/ns/sosa/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix unit: <http://qudt.org/vocab/unit/> .

sf:measuresVibration a sosa:ObservableProperty ;
    rdfs:label "vibration"@en, "振动"@zh ;
    sf:hasUnit unit:MilliM-PER-SEC ;
    sf:minValue "0.0"^^xsd:double ;
    sf:maxValue "50.0"^^xsd:double ;
    sf:belongsToSubsystem sf:VibrationSubsystem .

sf:VibrationSubsystem a sf:Subsystem ; rdfs:label "振动监测"@zh .
"""


@pytest.fixture
def registry():
    reg = MetaModelRegistry()
    reg.load_turtle(TEMP_TTL)
    return reg


def perfect_validator(payload):
    props = payload.get("measurements", [])
    if payload.get("schema_version") != "v1":
        return False, "missing version"
    if not props:
        return False, "empty"
    limits = {"temperature": (-40.0, 80.0, "celsius"), "vibration": (0.0, 50.0, "mm_per_sec")}
    for m in props:
        spec = limits.get(m["type"])
        if spec is None:
            return False, "unknown property"
        low, high, unit = spec
        if m["unit"] != unit:
            return False, "wrong unit"
        if not low <= m["value"] <= high:
            return False, "out of range"
    return True, "ok"


def permissive_validator(payload):
    return True, "accepts everything"


class TestGeneration:
    def test_cases_are_derived_per_property(self, registry):
        cases = generate_cases("d1", "temp_humidity", "mqtt", registry.properties())
        names = {c.case_id for c in cases}
        assert "temperature.nominal" in names
        assert "temperature.above_range" in names
        assert "temperature.wrong_unit" in names

    def test_bounds_come_from_the_ontology(self, registry):
        cases = generate_cases("d1", "temp_humidity", "mqtt", registry.properties())
        lower = next(c for c in cases if c.case_id == "temperature.lower_bound")
        assert lower.payload["measurements"][0]["value"] == -40.0

    def test_schema_cases_always_present(self, registry):
        cases = generate_cases("d1", "temp_humidity", "mqtt", registry.properties())
        names = {c.case_id for c in cases}
        assert "schema.missing_version" in names
        assert "schema.unknown_property" in names

    def test_new_property_generates_new_cases(self, registry):
        before = len(generate_cases("d1", "s", "mqtt", registry.properties()))
        registry.load_turtle(VIBRATION_TTL)
        after = len(generate_cases("d1", "s", "mqtt", registry.properties()))
        assert after == before + 6

    def test_no_cases_written_by_hand(self, registry):
        registry.load_turtle(VIBRATION_TTL)
        cases = generate_cases("d1", "s", "mqtt", registry.properties())
        assert any(c.property_name == "vibration" for c in cases)

    def test_every_case_states_why(self, registry):
        for case in generate_cases("d1", "s", "mqtt", registry.properties()):
            assert case.rationale_zh


class TestExecution:
    def test_correct_platform_is_conformant(self, registry):
        cert = run_kit(
            "d1", "temp_humidity", "mqtt", registry.properties(), "v1",
            validator=perfect_validator,
        )
        assert cert.conformant
        assert cert.failed == 0

    def test_permissive_platform_fails(self, registry):
        cert = run_kit(
            "d1", "temp_humidity", "mqtt", registry.properties(), "v1",
            validator=permissive_validator,
        )
        assert not cert.conformant
        assert cert.blocking_failures > 0

    def test_failure_names_the_case(self, registry):
        cert = run_kit(
            "d1", "temp_humidity", "mqtt", registry.properties(), "v1",
            validator=permissive_validator,
        )
        failed = {o.case.case_id for o in cert.outcomes if not o.passed}
        assert "temperature.above_range" in failed

    def test_advisory_failure_does_not_block(self, registry):
        def only_advisory_fails(payload):
            if payload.get("schema_version") != "v1":
                return False, "missing version"
            if not payload.get("measurements"):
                return True, "accepts empty"
            return perfect_validator(payload)

        cert = run_kit(
            "d1", "temp_humidity", "mqtt", registry.properties(), "v1",
            validator=only_advisory_fails,
        )
        assert cert.failed >= 1
        assert cert.conformant

    def test_certificate_records_ontology_version(self, registry):
        cert = run_kit(
            "d1", "s", "mqtt", registry.properties(), "abc123",
            validator=perfect_validator,
        )
        assert cert.ontology_version == "abc123"

    def test_certificate_serialises(self, registry):
        cert = run_kit(
            "d1", "s", "mqtt", registry.properties(), "v1",
            validator=perfect_validator,
        )
        assert "outcomes" in to_json(cert)

    def test_render_marks_pass_and_fail(self, registry):
        cert = run_kit(
            "d1", "s", "mqtt", registry.properties(), "v1",
            validator=permissive_validator,
        )
        text = render(cert)
        assert "FAIL" in text

    def test_summary_is_chinese(self, registry):
        cert = run_kit(
            "d1", "s", "mqtt", registry.properties(), "v1",
            validator=perfect_validator,
        )
        assert "一致性测试" in cert.summary_zh()

    def test_real_platform_gate_is_exercised(self, registry):
        cert = run_kit(
            "ESP32_001_dht22", "temp_humidity", "mqtt", registry.properties(), "v1"
        )
        assert cert.total > 0
        assert isinstance(cert.conformant, bool)
