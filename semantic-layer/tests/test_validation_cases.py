from pathlib import Path

import pytest

from semantic_layer.protocol_binding import (
    BindingRegistry,
    generate_all,
    validate_bindings,
)

CASES_DIR = Path(__file__).resolve().parents[2] / "validation" / "cases"


def load(filename: str) -> str:
    return (CASES_DIR / filename).read_text(encoding="utf-8")


def test_valid_address_is_accepted_and_generates_an_adapter():
    turtle = load("case1_valid_address.ttl")
    accepted, violations, _ = validate_bindings(turtle)
    assert accepted, violations

    registry = BindingRegistry()
    assert registry.load_turtle(turtle).accepted
    adapters = generate_all(registry)
    assert "modbus" in adapters
    assert "40001" in adapters["modbus"]

    binding = registry.for_protocol("modbus")[0]
    assert binding.register_address == 40001
    assert binding.wire_address == 0
    assert binding.register_type == "int16"
    assert binding.scale_factor == pytest.approx(0.01)


def test_illegal_address_is_rejected_at_load_time():
    accepted, violations, _ = validate_bindings(load("case2_illegal_address.ttl"))
    assert not accepted
    blob = " ".join(violations)
    assert "registerAddress" in blob
    assert "functionCode" in blob


def test_type_mismatch_is_rejected_at_load_time():
    accepted, violations, _ = validate_bindings(load("case3_type_mismatch.ttl"))
    assert not accepted
    blob = " ".join(violations)
    assert "registerType" in blob
    assert "scaleFactor" in blob
    assert "pollIntervalMs" in blob


@pytest.mark.parametrize(
    "filename", ["case2_illegal_address.ttl", "case3_type_mismatch.ttl"]
)
def test_rejected_bindings_never_enter_the_registry(filename):
    registry = BindingRegistry()
    result = registry.load_turtle(load(filename))
    assert not result.accepted
    assert result.bindings_added == []
    assert len(registry) == 0


def test_a_rejected_binding_cannot_reach_adapter_generation():
    registry = BindingRegistry()
    registry.load_turtle(load("case3_type_mismatch.ttl"))
    assert generate_all(registry) == {}