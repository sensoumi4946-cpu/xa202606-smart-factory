from __future__ import annotations

from pathlib import Path

import pytest

from semantic_layer.protocol_binding import (
    BindingRegistry,
    canonical_subsystem,
    decode_registers,
    generate_all,
)
from smart_factory_contracts.messages import UnifiedMessage

BINDINGS_TTL = Path(__file__).resolve().parents[2] / "bindings.ttl"

FIELD_PAYLOADS = [
    {
        "schema_version": "v1",
        "device_id": "ESP32_002",
        "subsystem": "counting",
        "protocol": "rest",
        "measurements": [{"type": "count", "value": 3.0, "unit": "count"}],
    },
    {
        "schema_version": "v1",
        "device_id": "ESP32_003",
        "subsystem": "lighting",
        "protocol": "rest",
        "measurements": [
            {"type": "occupancy", "value": 1.0, "unit": "boolean"},
            {"type": "light_state", "value": 0.0, "unit": "boolean"},
        ],
    },
    {
        "schema_version": "v1",
        "device_id": "ESP32_001",
        "subsystem": "temp_humidity",
        "protocol": "mqtt",
        "measurements": [
            {"type": "temperature", "value": 26.1, "unit": "celsius"},
            {"type": "humidity", "value": 56.2, "unit": "percent"},
        ],
    },
]


@pytest.fixture(scope="module")
def registry() -> BindingRegistry:
    reg = BindingRegistry()
    result = reg.load_turtle(BINDINGS_TTL.read_text(encoding="utf-8"))
    assert result.accepted, result.violations
    return reg


def test_bindings_file_is_discoverable():
    assert BINDINGS_TTL.exists()


def test_every_declared_protocol_has_a_generator(registry):
    declared = {b.protocol for b in registry.all()}
    generated = set(generate_all(registry))
    assert declared == generated, f"no generator for {sorted(declared - generated)}"


def test_rest_bindings_are_generated(registry):
    rest = generate_all(registry)["rest"]
    assert "ESP32_002" in rest and "ESP32_003" in rest


@pytest.mark.parametrize(
    "subsystem", ["temp_humidity", "lighting", "gas", "agv", "counting"]
)
def test_canonical_subsystem_strips_ontology_suffix(subsystem):
    assert canonical_subsystem(f"{subsystem}_subsystem") == subsystem


def test_generated_modbus_messages_satisfy_the_contract(registry):
    namespace: dict = {}
    exec(generate_all(registry)["modbus"], namespace)
    for entry in namespace["REGISTER_MAP"]:
        message = namespace["build_message"](entry, [100] * entry["count"])
        UnifiedMessage(**message)


def test_generated_rest_messages_satisfy_the_contract(registry):
    namespace: dict = {}
    exec(generate_all(registry)["rest"], namespace)
    for entry in namespace["ROUTE_MAP"]:
        message = namespace["build_message"](entry, 1)
        UnifiedMessage(**message)


def test_modbus_wire_address_removes_the_4xxxx_base(registry):
    by_property = {b.property_name: b for b in registry.for_protocol("modbus")}
    assert by_property["temperature"].register_address == 40001
    assert by_property["temperature"].wire_address == 0
    assert by_property["humidity"].wire_address == 1
    assert by_property["sensor_status"].wire_address == 4


def test_firmware_scaling_matches_the_declared_scale_factor(registry):
    temperature = next(
        b for b in registry.for_protocol("modbus") if b.property_name == "temperature"
    )
    decoded = decode_registers(
        [2610],
        register_type=temperature.register_type,
        word_order=temperature.word_order,
        byte_order=temperature.byte_order,
        scale_factor=temperature.scale_factor,
    )
    assert decoded == pytest.approx(26.1)


def test_negative_temperature_survives_the_signed_register(registry):
    temperature = next(
        b for b in registry.for_protocol("modbus") if b.property_name == "temperature"
    )
    assert temperature.register_type == "int16"
    decoded = decode_registers(
        [0xFDF8],
        register_type=temperature.register_type,
        scale_factor=temperature.scale_factor,
    )
    assert decoded == pytest.approx(-5.2)


def test_firmware_aliases_collapse_onto_one_device(registry):
    assert registry.resolve_device_id("ESP32_001_dht22") == "ESP32_001"
    assert registry.resolve_device_id("ESP32_002_ir") == "ESP32_002"
    assert registry.resolve_device_id("ESP32_003_pir") == "ESP32_003"
    assert registry.devices() == [
        "ESP32_001",
        "ESP32_002",
        "ESP32_003",
        "ESP32_004",
        "ESP32_005",
    ]


@pytest.mark.parametrize("payload", FIELD_PAYLOADS, ids=lambda p: p["device_id"])
def test_field_payloads_are_covered_by_a_binding(registry, payload):
    message = UnifiedMessage(**payload)
    canonical = registry.resolve_device_id(message.device_id)
    bindings = registry.for_device(canonical)
    assert bindings
    declared = {b.property_name for b in bindings}
    for measurement in message.measurements:
        assert measurement.type.value in declared


def test_modbus_binding_without_register_address_is_rejected():
    bad = """
    @prefix sf: <http://example.org/smart-factory#> .
    sf:broken a sf:ProtocolBinding ;
        sf:bindsProperty sf:measuresTemperature ;
        sf:transportProtocol "modbus" ;
        sf:deviceId "ESP32_099" .
    """
    result = BindingRegistry().load_turtle(bad)
    assert not result.accepted
    assert any("registerAddress" in v for v in result.violations)


def test_checked_in_generated_adapters_are_up_to_date(registry):
    root = BINDINGS_TTL.parent
    for protocol, source in generate_all(registry).items():
        path = root / f"generated_{protocol}_adapter.py"
        assert path.exists(), f"{path.name} missing; run make generate-adapters"
        assert path.read_text(encoding="utf-8") == source
