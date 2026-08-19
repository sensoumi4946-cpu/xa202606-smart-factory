import json

import pytest

from analytics.policy_verifier import (
    Certificate,
    RuleCondition,
    VerifiedPolicy,
    check_reachable,
    _collect_variables,
    from_safety_controller,
    verify,
    verify_controller,
)
from analytics.safety_controller import Policy, SafetyController


def policy(name, device, engage, release, conditions, label="策略"):
    return VerifiedPolicy(
        name=name,
        label_zh=label,
        target_device=device,
        engage_action=engage,
        release_action=release,
        conditions=[RuleCondition(*c) for c in conditions],
    )


class TestRealPolicySet:
    def test_shipped_policies_are_conflict_free(self):
        cert = verify_controller(SafetyController())
        assert cert.verified is True
        assert cert.conflicts == []

    def test_certificate_counts_every_pair(self):
        cert = verify_controller(SafetyController())
        n = cert.policy_count
        assert cert.pair_count == n * (n - 1) // 2

    def test_certificate_names_the_solver(self):
        cert = verify_controller(SafetyController())
        assert cert.solver_version

    def test_certificate_is_json_serialisable(self):
        json.dumps(verify_controller(SafetyController()).to_dict())

    def test_summary_is_chinese_and_quantified(self):
        cert = verify_controller(SafetyController())
        text = cert.summary_zh()
        assert "形式化验证" in text
        assert str(cert.policy_count) in text

    def test_no_policy_is_unreachable(self):
        cert = verify_controller(SafetyController())
        assert cert.unreachable_policies == []

    def test_conditions_are_derived_from_hazard_rules(self):
        policies = from_safety_controller(SafetyController())
        gas = next(p for p in policies if p.name == "gas_isolation")
        names = {c.property_name for c in gas.conditions}
        assert "combustible_gas" in names


class TestConflictDetection:
    def test_opposing_actions_on_one_device_are_caught(self):
        cert = verify(
            [
                policy("a", "valve", "open", "close", [("co", 10.0, "above")]),
                policy("b", "valve", "close", "open", [("temperature", 30.0, "above")]),
            ]
        )
        assert cert.verified is False
        assert len(cert.conflicts) == 1
        assert cert.conflicts[0].kind == "opposing_actions"

    def test_conflict_reports_a_concrete_witness(self):
        cert = verify(
            [
                policy("a", "valve", "open", "close", [("co", 10.0, "above")]),
                policy("b", "valve", "close", "open", [("temperature", 30.0, "above")]),
            ]
        )
        witness = cert.conflicts[0].witness
        assert witness["co"] > 10.0
        assert witness["temperature"] > 30.0

    def test_witness_actually_satisfies_both_policies(self):
        a = policy("a", "valve", "open", "close", [("co", 10.0, "above")])
        b = policy("b", "valve", "close", "open", [("temperature", 30.0, "above")])
        witness = verify([a, b]).conflicts[0].witness
        for p in (a, b):
            for c in p.conditions:
                value = witness[c.property_name]
                if c.direction == "above":
                    assert value > c.threshold
                else:
                    assert value < c.threshold

    def test_explanation_names_both_policies(self):
        cert = verify(
            [
                policy("gas_open", "valve", "open", "close", [("co", 10.0, "above")]),
                policy("gas_shut", "valve", "close", "open", [("co", 20.0, "above")]),
            ]
        )
        text = cert.conflicts[0].explanation_zh
        assert "gas_open" in text
        assert "gas_shut" in text
        assert "冲突" in text

    def test_on_off_pair_is_opposing(self):
        cert = verify(
            [
                policy("a", "hvac", "on", "off", [("temperature", 30.0, "above")]),
                policy("b", "hvac", "off", "on", [("humidity", 50.0, "above")]),
            ]
        )
        assert not cert.verified

    def test_start_stop_pair_is_opposing(self):
        cert = verify(
            [
                policy("a", "pump", "start", "stop", [("pressure", 100.0, "above")]),
                policy("b", "pump", "stop", "start", [("pressure", 900.0, "above")]),
            ]
        )
        assert not cert.verified


class TestNonConflicts:
    def test_different_devices_never_conflict(self):
        cert = verify(
            [
                policy("a", "valve", "open", "close", [("co", 10.0, "above")]),
                policy("b", "hvac", "close", "open", [("co", 10.0, "above")]),
            ]
        )
        assert cert.verified

    def test_same_action_is_not_a_conflict(self):
        cert = verify(
            [
                policy("a", "valve", "close", "open", [("co", 10.0, "above")]),
                policy("b", "valve", "close", "open", [("smoke", 5.0, "above")]),
            ]
        )
        assert cert.verified

    def test_mutually_exclusive_conditions_are_safe(self):
        cert = verify(
            [
                policy("a", "valve", "open", "close", [("co", 100.0, "above")]),
                policy("b", "valve", "close", "open", [("co", 10.0, "below")]),
            ]
        )
        assert cert.verified

    def test_domain_bounds_make_impossible_overlaps_safe(self):
        cert = verify(
            [
                policy("a", "valve", "open", "close", [("occupancy", 0.9, "above")]),
                policy("b", "valve", "close", "open", [("occupancy", 0.1, "below")]),
            ]
        )
        assert cert.verified

    def test_single_policy_has_no_pairs(self):
        cert = verify([policy("a", "valve", "close", "open", [("co", 10.0, "above")])])
        assert cert.verified
        assert cert.pair_count == 0

    def test_empty_policy_set_verifies(self):
        cert = verify([])
        assert cert.verified
        assert cert.policy_count == 0


class TestReachability:
    def test_contradictory_policy_is_unreachable(self):
        cert = verify(
            [
                policy(
                    "impossible",
                    "valve",
                    "close",
                    "open",
                    [("co", 100.0, "above"), ("co", 10.0, "below")],
                )
            ]
        )
        assert "impossible" in cert.unreachable_policies

    def test_out_of_domain_policy_is_unreachable(self):
        cert = verify(
            [policy("silly", "valve", "close", "open", [("humidity", 500.0, "above")])]
        )
        assert "silly" in cert.unreachable_policies

    def test_reachable_policy_is_not_flagged(self):
        p = policy("fine", "valve", "close", "open", [("co", 35.0, "above")])
        assert check_reachable(p, _collect_variables([p]))

    def test_unreachable_policy_does_not_break_verification(self):
        cert = verify(
            [
                policy(
                    "impossible",
                    "valve",
                    "open",
                    "close",
                    [("co", 100.0, "above"), ("co", 10.0, "below")],
                ),
                policy("fine", "valve", "close", "open", [("co", 35.0, "above")]),
            ]
        )
        assert cert.verified is True
        assert cert.unreachable_policies == ["impossible"]


class TestCertificateIntegrity:
    def test_fingerprint_is_stable(self):
        policies = from_safety_controller(SafetyController())
        assert verify(policies).fingerprint == verify(policies).fingerprint

    def test_fingerprint_changes_when_a_policy_changes(self):
        base = verify_controller(SafetyController()).fingerprint

        controller = SafetyController()
        controller.policies.append(
            Policy(
                name="rogue",
                label_zh="错误策略",
                hazard_rules=("fire_risk",),
                target_device="valve_gas_main",
                target_subsystem="gas",
                engage_action="open",
                release_action="close",
            )
        )
        assert verify_controller(controller).fingerprint != base

    def test_injected_conflicting_policy_is_caught(self):
        controller = SafetyController()
        controller.policies.append(
            Policy(
                name="rogue_valve_open",
                label_zh="错误开阀",
                hazard_rules=("fire_risk",),
                target_device="valve_gas_main",
                target_subsystem="gas",
                engage_action="open",
                release_action="close",
            )
        )
        cert = verify_controller(controller)
        assert cert.verified is False
        assert any(
            c.target_device == "valve_gas_main" for c in cert.conflicts
        )

    def test_failed_certificate_summary_reports_count(self):
        cert = verify(
            [
                policy("a", "valve", "open", "close", [("co", 10.0, "above")]),
                policy("b", "valve", "close", "open", [("co", 20.0, "above")]),
            ]
        )
        assert "验证未通过" in cert.summary_zh()

    def test_certificate_records_generation_time(self):
        assert verify_controller(SafetyController()).generated_at
