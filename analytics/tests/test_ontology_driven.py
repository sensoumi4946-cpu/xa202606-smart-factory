import pytest

from analytics.anomaly_detector import AnomalyDetector
from analytics.fault_predictor import FaultPredictor
from analytics.hazard_reasoner import HazardReasoner
from analytics.thresholds import FALLBACK_THRESHOLDS, ThresholdResolver, resolver
from semantic_layer.meta_model import MetaModelRegistry

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

sf:VibrationSubsystem a sf:Subsystem ; rdfs:label "振动监测"@zh .
"""

RETUNED_CO = """
@prefix sf:   <http://example.org/smart-factory#> .
@prefix sosa: <http://www.w3.org/ns/sosa/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix unit: <http://qudt.org/vocab/unit/> .

sf:measuresCo a sosa:ObservableProperty ;
    rdfs:label "co"@en, "一氧化碳"@zh ;
    sf:hasUnit unit:PPM ;
    sf:minValue "0.0"^^xsd:double ;
    sf:maxValue "1000.0"^^xsd:double ;
    sf:warnThreshold "8.0"^^xsd:double ;
    sf:dangerThreshold "12.0"^^xsd:double ;
    sf:belongsToSubsystem sf:GasSubsystem .

sf:GasSubsystem a sf:Subsystem ; rdfs:label "危险气体"@zh .
"""


@pytest.fixture
def registry():
    return MetaModelRegistry()


@pytest.fixture(autouse=True)
def _unbind():
    resolver.unbind()
    yield
    resolver.unbind()


class TestResolver:
    def test_falls_back_before_any_ontology(self):
        r = ThresholdResolver()
        assert r.threshold_for("co") == FALLBACK_THRESHOLDS["co"]
        assert r.resolve_source("co") == "fallback"

    def test_unknown_property_before_loading(self):
        r = ThresholdResolver()
        assert r.threshold_for("vibration") is None
        assert r.resolve_source("vibration") == "unknown"

    def test_ontology_supplies_new_property(self, registry):
        registry.load_turtle(VIBRATION)
        r = ThresholdResolver()
        r.bind(registry)
        assert r.threshold_for("vibration") == (15.0, "above")
        assert r.limit_for("vibration") == (0.0, 50.0)
        assert r.resolve_source("vibration") == "ontology"

    def test_ontology_overrides_the_fallback(self, registry):
        registry.load_turtle(RETUNED_CO)
        r = ThresholdResolver()
        r.bind(registry)
        assert FALLBACK_THRESHOLDS["co"][0] == 35.0
        assert r.threshold_for("co") == (12.0, "above")

    def test_warn_threshold_comes_from_the_graph(self, registry):
        registry.load_turtle(VIBRATION)
        r = ThresholdResolver()
        r.bind(registry)
        assert r.warn_for("vibration") == 8.0

    def test_report_separates_the_two_sources(self, registry):
        registry.load_turtle(VIBRATION)
        r = ThresholdResolver()
        r.bind(registry)
        report = r.report()
        assert "vibration" in report["from_ontology"]
        assert "temperature" in report["from_fallback"]

    def test_version_tracks_the_registry(self, registry):
        r = ThresholdResolver()
        assert r.version == "fallback"
        r.bind(registry)
        before = r.version
        registry.load_turtle(VIBRATION)
        assert r.version != before


class TestAnomalyDetectorFollowsOntology:
    def test_unknown_property_has_no_range_check(self):
        detector = AnomalyDetector()
        result = detector.push_reading("vib_01", 9999.0, property_name="vibration")
        assert result.is_anomaly is False

    def test_loaded_property_gains_a_range_check(self, registry):
        registry.load_turtle(VIBRATION)
        resolver.bind(registry)
        detector = AnomalyDetector()
        result = detector.push_reading("vib_01", 9999.0, property_name="vibration")
        assert result.is_anomaly is True

    def test_in_range_value_is_not_flagged(self, registry):
        registry.load_turtle(VIBRATION)
        resolver.bind(registry)
        detector = AnomalyDetector()
        result = detector.push_reading("vib_01", 12.0, property_name="vibration")
        assert result.is_anomaly is False


class TestPredictorFollowsOntology:
    def test_unknown_property_is_not_predicted(self):
        predictor = FaultPredictor()
        last = None
        for i in range(8):
            last = predictor.push("vib_01", "vibration", 1.0 + i, timestamp=float(i))
        assert last is None

    def test_loaded_property_becomes_predictable(self, registry):
        registry.load_turtle(VIBRATION)
        resolver.bind(registry)
        predictor = FaultPredictor()
        last = None
        for i in range(8):
            last = predictor.push("vib_01", "vibration", 1.0 + i, timestamp=float(i))
        assert last is not None
        assert last.threshold == 15.0
        assert last.seconds_to_threshold is not None

    def test_retuned_threshold_changes_the_forecast(self, registry):
        predictor = FaultPredictor()
        for i in range(8):
            baseline = predictor.push("mq2", "co", 1.0 + i, timestamp=float(i))
        assert baseline is not None
        assert baseline.threshold == 35.0

        registry.load_turtle(RETUNED_CO)
        resolver.bind(registry)
        predictor2 = FaultPredictor()
        for i in range(8):
            tuned = predictor2.push("mq2", "co", 1.0 + i, timestamp=float(i))
        assert tuned is not None
        assert tuned.threshold == 12.0

    def test_explicit_override_still_wins(self, registry):
        registry.load_turtle(RETUNED_CO)
        resolver.bind(registry)
        predictor = FaultPredictor(thresholds={"co": (99.0, "above")})
        last = None
        for i in range(10):
            last = predictor.push("mq2", "co", 50.0 + i * 5, timestamp=float(i))
        assert last is not None
        assert last.threshold == 99.0


class TestHazardRulesFollowOntology:
    def test_rule_uses_the_declared_threshold_by_default(self):
        reasoner = HazardReasoner()
        alerts = reasoner.observe(
            "mix",
            "gas",
            "modbus",
            [{"type": "co", "value": 20.0}, {"type": "temperature", "value": 45.0}],
            timestamp=100.0,
        )
        assert alerts == []

    def test_retuned_ontology_makes_the_rule_fire_earlier(self, registry):
        registry.load_turtle(RETUNED_CO)
        resolver.bind(registry)
        reasoner = HazardReasoner()
        alerts = reasoner.observe(
            "mix",
            "gas",
            "modbus",
            [{"type": "co", "value": 20.0}, {"type": "temperature", "value": 45.0}],
            timestamp=100.0,
        )
        assert any(a.rule_name == "fire_risk" for a in alerts)

    def test_opting_out_pins_the_rule_to_its_own_numbers(self, registry):
        registry.load_turtle(RETUNED_CO)
        resolver.bind(registry)
        reasoner = HazardReasoner(use_ontology_thresholds=False)
        alerts = reasoner.observe(
            "mix",
            "gas",
            "modbus",
            [{"type": "co", "value": 20.0}, {"type": "temperature", "value": 45.0}],
            timestamp=100.0,
        )
        assert alerts == []


class TestNoCodeChangeClaim:
    def test_new_sensor_reaches_all_three_modules_at_once(self, registry):
        detector = AnomalyDetector()
        predictor = FaultPredictor()

        assert detector.push_reading("v", 9999.0, property_name="vibration").is_anomaly is False
        assert predictor.push("v", "vibration", 1.0, timestamp=0.0) is None

        registry.load_turtle(VIBRATION)
        resolver.bind(registry)

        assert detector.push_reading("v2", 9999.0, property_name="vibration").is_anomaly is True

        predictor2 = FaultPredictor()
        last = None
        for i in range(8):
            last = predictor2.push("v2", "vibration", 1.0 + i, timestamp=float(i))
        assert last is not None
        assert "vibration" in resolver.report()["from_ontology"]
