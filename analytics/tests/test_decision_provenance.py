import json

import pytest

from analytics.decision_provenance import (
    DecisionLedger,
    EvidenceLink,
    evidence_from_hazard,
)

FIRE_HAZARD = {
    "rule_name": "fire_risk",
    "label_zh": "火灾风险",
    "severity": "critical",
    "confidence": "high",
    "evidence": [
        {
            "device_id": "esp32_02_mq2",
            "subsystem": "gas",
            "protocol": "modbus",
            "property_name": "co",
            "value": 50.0,
            "threshold": 35.0,
            "observed_at": 100.0,
        },
        {
            "device_id": "esp32_01_dht22",
            "subsystem": "temp_humidity",
            "protocol": "mqtt",
            "property_name": "temperature",
            "value": 45.0,
            "threshold": 38.0,
            "observed_at": 101.0,
        },
    ],
}


@pytest.fixture
def led():
    return DecisionLedger()


def record_fire(led, command_id="cmd-1", version="abc123"):
    return led.record(
        policy_name="fire_ventilation",
        label_zh="火灾排风",
        hazard=FIRE_HAZARD,
        target_device="hvac_exhaust_01",
        action="on",
        params={"speed": 100},
        severity="critical",
        ontology_version=version,
        command_id=command_id,
    )


class TestEvidence:
    def test_parses_hazard_evidence(self):
        links = evidence_from_hazard(FIRE_HAZARD)
        assert len(links) == 2
        assert all(isinstance(link, EvidenceLink) for link in links)

    def test_skips_malformed_entries(self):
        bad = {"evidence": [{"value": "not a number"}, FIRE_HAZARD["evidence"][0]]}
        assert len(evidence_from_hazard(bad)) == 1

    def test_hazard_without_evidence_yields_nothing(self):
        assert evidence_from_hazard({"rule_name": "x"}) == []

    def test_sentence_names_the_protocol(self):
        link = evidence_from_hazard(FIRE_HAZARD)[0]
        assert "MODBUS" in link.sentence()
        assert "50.0" in link.sentence()


class TestDecisionRecord:
    def test_records_the_triggering_rule(self, led):
        d = record_fire(led)
        assert d.hazard_rule == "fire_risk"
        assert d.policy_name == "fire_ventilation"

    def test_captures_ontology_version(self, led):
        d = record_fire(led, version="v9f8e7")
        assert d.ontology_version == "v9f8e7"

    def test_lists_both_subsystems(self, led):
        d = record_fire(led)
        assert d.subsystems == ["gas", "temp_humidity"]

    def test_lists_both_protocols(self, led):
        d = record_fire(led)
        assert d.protocols == ["modbus", "mqtt"]

    def test_causal_chain_is_ordered_by_observation_time(self, led):
        d = record_fire(led)
        chain = d.causal_chain()
        assert len(chain) == 2
        assert "co=50.0" in chain[0]
        assert "temperature=45.0" in chain[1]

    def test_chinese_explanation_names_cause_and_effect(self, led):
        d = record_fire(led)
        text = d.explanation_zh()
        assert "fire_risk" in text
        assert "hvac_exhaust_01" in text
        assert "MODBUS + MQTT" in text
        assert "语义层" in text

    def test_fingerprint_is_stable(self, led):
        d = record_fire(led)
        assert d.fingerprint() == d.fingerprint()

    def test_fingerprint_changes_with_action(self, led):
        first = record_fire(led).fingerprint()
        second = led.record(
            policy_name="fire_ventilation",
            label_zh="火灾排风",
            hazard=FIRE_HAZARD,
            target_device="hvac_exhaust_01",
            action="off",
            params={"speed": 100},
            severity="critical",
            ontology_version="abc123",
        ).fingerprint()
        assert first != second

    def test_fingerprint_changes_with_ontology_version(self, led):
        a = record_fire(led, version="v1").fingerprint()
        b = record_fire(led, version="v2").fingerprint()
        assert a != b

    def test_record_is_json_serialisable(self, led):
        json.dumps(record_fire(led).to_dict())


class TestLedger:
    def test_starts_empty(self, led):
        assert len(led) == 0

    def test_lookup_by_id(self, led):
        d = record_fire(led)
        assert led.get(d.decision_id) is d

    def test_lookup_by_command_id(self, led):
        d = record_fire(led, command_id="cmd-42")
        assert led.by_command("cmd-42").decision_id == d.decision_id

    def test_unknown_id_returns_none(self, led):
        assert led.get("nope") is None
        assert led.by_command("nope") is None

    def test_attach_audit_links_the_chain(self, led):
        d = record_fire(led)
        led.attach_audit(d.decision_id, 7, "deadbeef")
        assert led.get(d.decision_id).audit_seq == 7
        assert led.get(d.decision_id).audit_hash == "deadbeef"

    def test_outcome_can_be_updated(self, led):
        d = record_fire(led)
        assert d.outcome == "pending"
        led.set_outcome(d.decision_id, "executed")
        assert led.get(d.decision_id).outcome == "executed"

    def test_filter_by_policy(self, led):
        record_fire(led)
        led.record(
            policy_name="gas_isolation",
            label_zh="燃气紧急切断",
            hazard={"rule_name": "gas_leak_unattended", "evidence": []},
            target_device="valve_gas_main",
            action="close",
            params={},
            severity="critical",
            ontology_version="abc",
        )
        assert len(led.list(policy_name="gas_isolation")) == 1

    def test_filter_by_severity(self, led):
        record_fire(led)
        led.record(
            policy_name="hvac_dehumidify",
            label_zh="除湿通风",
            hazard={"rule_name": "condensation_risk", "evidence": []},
            target_device="hvac_exhaust_01",
            action="on",
            params={},
            severity="warning",
            ontology_version="abc",
        )
        assert len(led.list(severity="warning")) == 1

    def test_newest_first(self, led):
        first = record_fire(led, command_id="c1")
        second = record_fire(led, command_id="c2")
        assert led.list()[0].decision_id == second.decision_id
        assert led.list()[1].decision_id == first.decision_id

    def test_bounded_size(self):
        led = DecisionLedger(max_records=3)
        for i in range(10):
            record_fire(led, command_id=f"c{i}")
        assert len(led) == 3

    def test_reset_clears(self, led):
        record_fire(led)
        led.reset()
        assert len(led) == 0
