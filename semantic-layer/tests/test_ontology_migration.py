import pytest

from semantic_layer.ontology_migration import (
    CHANGE_ADD,
    CHANGE_NARROW_RANGE,
    CHANGE_REMOVE,
    CHANGE_RENAME,
    CHANGE_UNIT,
    CHANGE_WIDEN_RANGE,
    diff,
    plan_migration,
    render,
    rewrite_query,
    snapshot,
    to_json,
)
from rdflib import Graph

HEAD = """
@prefix sf:   <http://example.org/smart-factory#> .
@prefix sosa: <http://www.w3.org/ns/sosa/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix unit: <http://qudt.org/vocab/unit/> .
"""


def prop(name, label, unit="unit:DEG_C", low="-40.0", high="80.0"):
    camel = "".join(p.capitalize() for p in name.split("_"))
    return f"""
sf:measures{camel} a sosa:ObservableProperty ;
    rdfs:label "{label}"@en ;
    sf:hasUnit {unit} ;
    sf:minValue "{low}"^^xsd:double ;
    sf:maxValue "{high}"^^xsd:double ;
    sf:belongsToSubsystem sf:S .
"""


V1 = HEAD + prop("temperature", "air temperature") + prop("humidity", "relative humidity", "unit:PERCENT", "0.0", "100.0")
V2_RENAME = HEAD + prop("air_temperature", "air temperature") + prop("humidity", "relative humidity", "unit:PERCENT", "0.0", "100.0")
V2_ADD = V1 + prop("vibration", "vibration", "unit:MilliM-PER-SEC", "0.0", "50.0")
V2_REMOVE = HEAD + prop("temperature", "air temperature")
V2_UNIT = HEAD + prop("temperature", "air temperature", "unit:DEG_F") + prop("humidity", "relative humidity", "unit:PERCENT", "0.0", "100.0")
V2_NARROW = HEAD + prop("temperature", "air temperature", "unit:DEG_C", "0.0", "50.0") + prop("humidity", "relative humidity", "unit:PERCENT", "0.0", "100.0")
V2_WIDEN = HEAD + prop("temperature", "air temperature", "unit:DEG_C", "-60.0", "150.0") + prop("humidity", "relative humidity", "unit:PERCENT", "0.0", "100.0")


def graphs(a, b):
    ga, gb = Graph(), Graph()
    ga.parse(data=a, format="turtle")
    gb.parse(data=b, format="turtle")
    return ga, gb


class TestSnapshot:
    def test_reads_properties(self):
        g = Graph()
        g.parse(data=V1, format="turtle")
        snap = snapshot(g)
        assert set(snap) == {"temperature", "humidity"}
        assert snap["temperature"].min_value == -40.0


class TestDiff:
    def test_rename_is_detected(self):
        changes = diff(*graphs(V1, V2_RENAME))
        renames = [c for c in changes if c.kind == CHANGE_RENAME]
        assert len(renames) == 1
        assert renames[0].before == "temperature"
        assert renames[0].after == "air_temperature"

    def test_rename_is_not_breaking(self):
        changes = diff(*graphs(V1, V2_RENAME))
        assert all(not c.breaking for c in changes)

    def test_addition_is_not_breaking(self):
        changes = diff(*graphs(V1, V2_ADD))
        adds = [c for c in changes if c.kind == CHANGE_ADD]
        assert adds and not adds[0].breaking

    def test_removal_is_breaking(self):
        changes = diff(*graphs(V1, V2_REMOVE))
        removes = [c for c in changes if c.kind == CHANGE_REMOVE]
        assert removes and removes[0].breaking

    def test_unit_change_is_breaking(self):
        changes = diff(*graphs(V1, V2_UNIT))
        units = [c for c in changes if c.kind == CHANGE_UNIT]
        assert units and units[0].breaking

    def test_narrowing_range_is_breaking(self):
        changes = diff(*graphs(V1, V2_NARROW))
        narrow = [c for c in changes if c.kind == CHANGE_NARROW_RANGE]
        assert narrow and narrow[0].breaking

    def test_widening_range_is_safe(self):
        changes = diff(*graphs(V1, V2_WIDEN))
        widen = [c for c in changes if c.kind == CHANGE_WIDEN_RANGE]
        assert widen and not widen[0].breaking

    def test_identical_ontologies_have_no_changes(self):
        assert diff(*graphs(V1, V1)) == []


class TestPlan:
    def test_compatible_plan_is_accepted(self):
        plan = plan_migration(V1, V2_RENAME)
        assert plan.compatible
        assert not plan.blocked_reasons

    def test_breaking_plan_is_blocked(self):
        plan = plan_migration(V1, V2_REMOVE)
        assert not plan.compatible
        assert plan.blocked_reasons

    def test_breaking_plan_can_be_forced(self):
        plan = plan_migration(V1, V2_REMOVE, allow_breaking=True)
        assert plan.compatible

    def test_alignment_axioms_generated_for_renames(self):
        plan = plan_migration(V1, V2_RENAME)
        assert "owl:equivalentProperty" in plan.alignment_axioms

    def test_alignment_axioms_are_valid_turtle(self):
        plan = plan_migration(V1, V2_RENAME)
        g = Graph()
        g.parse(data=plan.alignment_axioms, format="turtle")
        assert len(g) > 0

    def test_no_axioms_when_nothing_renamed(self):
        assert plan_migration(V1, V2_ADD).alignment_axioms == ""

    def test_summary_explains_the_outcome(self):
        assert "兼容" in plan_migration(V1, V2_RENAME).summary_zh()
        assert "阻断" in plan_migration(V1, V2_REMOVE).summary_zh()

    def test_plan_serialises(self):
        assert "changes" in to_json(plan_migration(V1, V2_RENAME))

    def test_render_marks_breaking_changes(self):
        assert "BREAK" in render(plan_migration(V1, V2_REMOVE))


class TestQueryRewrite:
    def test_renamed_property_is_rewritten(self):
        plan = plan_migration(V1, V2_RENAME)
        old = "SELECT ?v WHERE { ?o sosa:observedProperty sf:measuresTemperature } LIMIT 10"
        new = rewrite_query(old, plan.changes)
        assert "sf:measuresAirTemperature" in new
        assert "sf:measuresTemperature" not in new

    def test_untouched_property_is_left_alone(self):
        plan = plan_migration(V1, V2_RENAME)
        old = "SELECT ?v WHERE { ?o sosa:observedProperty sf:measuresHumidity } LIMIT 10"
        assert rewrite_query(old, plan.changes) == old

    def test_v1_query_answers_against_v2_after_rewrite(self):
        plan = plan_migration(V1, V2_RENAME)
        rewritten = rewrite_query('?o sf:name "temperature"', plan.changes)
        assert "air_temperature" in rewritten
