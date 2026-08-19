import pytest

from semantic_layer.meta_model import (
    MetaModelRegistry,
    PropertyDefinition,
    validate_fragment,
)

VIBRATION = """
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
    sf:warnThreshold "8.0"^^xsd:double ;
    sf:dangerThreshold "15.0"^^xsd:double ;
    sf:belongsToSubsystem sf:VibrationSubsystem .

sf:VibrationSubsystem a sf:Subsystem ;
    rdfs:label "vibration monitoring"@en, "振动监测"@zh .
"""

PRESSURE = """
@prefix sf:   <http://example.org/smart-factory#> .
@prefix sosa: <http://www.w3.org/ns/sosa/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix unit: <http://qudt.org/vocab/unit/> .

sf:measuresPressure a sosa:ObservableProperty ;
    rdfs:label "pressure"@en, "压力"@zh ;
    sf:hasUnit unit:KiloPA ;
    sf:minValue "0.0"^^xsd:double ;
    sf:maxValue "1000.0"^^xsd:double ;
    sf:dangerThreshold "800.0"^^xsd:double ;
    sf:belongsToSubsystem sf:PneumaticSubsystem .

sf:PneumaticSubsystem a sf:Subsystem ;
    rdfs:label "pneumatics"@en, "气动系统"@zh .
"""

MISSING_UNIT = """
@prefix sf:   <http://example.org/smart-factory#> .
@prefix sosa: <http://www.w3.org/ns/sosa/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

sf:measuresTorque a sosa:ObservableProperty ;
    rdfs:label "torque"@en ;
    sf:minValue "0.0"^^xsd:double ;
    sf:maxValue "100.0"^^xsd:double ;
    sf:belongsToSubsystem sf:DriveSubsystem .

sf:DriveSubsystem a sf:Subsystem ; rdfs:label "drive"@en .
"""

MISSING_LABEL = """
@prefix sf:   <http://example.org/smart-factory#> .
@prefix sosa: <http://www.w3.org/ns/sosa/> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix unit: <http://qudt.org/vocab/unit/> .

sf:measuresFlow a sosa:ObservableProperty ;
    sf:hasUnit unit:L-PER-MIN ;
    sf:minValue "0.0"^^xsd:double ;
    sf:maxValue "200.0"^^xsd:double ;
    sf:belongsToSubsystem sf:FlowSubsystem .

sf:FlowSubsystem a sf:Subsystem .
"""


@pytest.fixture
def reg():
    return MetaModelRegistry()


class TestValidation:
    def test_valid_fragment_accepted(self):
        ok, violations, graph = validate_fragment(VIBRATION)
        assert ok
        assert violations == []
        assert len(graph) > 0

    def test_broken_turtle_rejected(self):
        ok, violations, _ = validate_fragment("this is not turtle {{{")
        assert not ok
        assert "parse error" in violations[0]

    def test_empty_fragment_rejected(self):
        ok, violations, _ = validate_fragment("@prefix sf: <http://x#> .")
        assert not ok

    def test_fragment_without_property_or_subsystem_rejected(self):
        ok, violations, _ = validate_fragment(
            '@prefix ex: <http://x#> . ex:a ex:b "c" .'
        )
        assert not ok
        assert "declares no" in violations[0]

    def test_property_without_unit_rejected(self):
        ok, violations, _ = validate_fragment(MISSING_UNIT)
        assert not ok
        assert any("hasUnit" in v for v in violations)

    def test_property_without_label_rejected(self):
        ok, violations, _ = validate_fragment(MISSING_LABEL)
        assert not ok
        assert any("label" in v for v in violations)


class TestRegistry:
    def test_starts_empty(self, reg):
        assert reg.properties() == {}
        assert reg.dashboard_fields() == []

    def test_loading_adds_a_property(self, reg):
        result = reg.load_turtle(VIBRATION)
        assert result.accepted
        assert "vibration" in result.properties_added
        assert reg.knows("vibration")

    def test_property_carries_full_definition(self, reg):
        reg.load_turtle(VIBRATION)
        prop = reg.get("vibration")
        assert isinstance(prop, PropertyDefinition)
        assert prop.labels["zh"] == "振动"
        assert prop.min_value == 0.0
        assert prop.max_value == 50.0
        assert prop.warn_threshold == 8.0
        assert prop.danger_threshold == 15.0
        assert prop.subsystem == "vibration_subsystem"

    def test_subsystem_registered(self, reg):
        reg.load_turtle(VIBRATION)
        assert "vibration_subsystem" in reg.subsystems()

    def test_version_changes_after_load(self, reg):
        before = reg.version
        reg.load_turtle(VIBRATION)
        assert reg.version != before

    def test_version_is_stable_for_same_content(self, reg):
        reg.load_turtle(VIBRATION)
        first = reg.version
        reg.load_turtle(VIBRATION)
        assert reg.version == first

    def test_rejected_fragment_does_not_change_version(self, reg):
        reg.load_turtle(VIBRATION)
        before = reg.version
        result = reg.load_turtle(MISSING_UNIT)
        assert not result.accepted
        assert reg.version == before

    def test_rejected_fragment_adds_nothing(self, reg):
        reg.load_turtle(MISSING_UNIT)
        assert reg.properties() == {}

    def test_two_fragments_coexist(self, reg):
        reg.load_turtle(VIBRATION)
        reg.load_turtle(PRESSURE)
        assert reg.knows("vibration")
        assert reg.knows("pressure")
        assert len(reg.subsystems()) == 2

    def test_hard_limits_derived_from_graph(self, reg):
        reg.load_turtle(VIBRATION)
        assert reg.hard_limits()["vibration"] == (0.0, 50.0)

    def test_thresholds_derived_from_graph(self, reg):
        reg.load_turtle(VIBRATION)
        threshold, direction = reg.thresholds()["vibration"]
        assert threshold == 15.0
        assert direction == "high"

    def test_dashboard_fields_use_chinese_labels(self, reg):
        reg.load_turtle(VIBRATION)
        field = reg.dashboard_fields()[0]
        assert field["key"] == "vibration"
        assert field["label"] == "振动"
        assert field["danger"] == 15.0

    def test_history_records_both_outcomes(self, reg):
        reg.load_turtle(VIBRATION)
        reg.load_turtle(MISSING_UNIT)
        history = reg.history()
        assert len(history) == 2
        assert history[0]["accepted"] is False
        assert history[1]["accepted"] is True

    def test_reset_clears_everything(self, reg):
        reg.load_turtle(VIBRATION)
        reg.reset()
        assert reg.properties() == {}
        assert reg.subsystems() == {}

    def test_serialize_round_trips(self, reg):
        reg.load_turtle(VIBRATION)
        turtle = reg.serialize("turtle")
        fresh = MetaModelRegistry()
        assert fresh.load_turtle(turtle).accepted
        assert fresh.knows("vibration")

    def test_no_code_change_needed_for_new_type(self, reg):
        assert not reg.knows("pressure")
        reg.load_turtle(PRESSURE)
        assert reg.knows("pressure")
        assert reg.hard_limits()["pressure"] == (0.0, 1000.0)
        assert any(f["key"] == "pressure" for f in reg.dashboard_fields())
