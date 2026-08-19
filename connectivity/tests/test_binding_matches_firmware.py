from pathlib import Path

import pytest

from connectivity.generated_adapters import load_adapter_set

REPO_ROOT = Path(__file__).resolve().parents[2]
BINDINGS = REPO_ROOT / "bindings.ttl"

FIRMWARE_REGISTERS = {
    "temperature": 0,
    "humidity": 1,
}

FIRMWARE_STATUS_REGISTERS = {
    "device_status": 2,
    "error_code": 3,
    "sensor_status": 4,
}

FIRMWARE_SCALING = 100.0


@pytest.fixture(scope="module")
def adapters():
    if not BINDINGS.exists():
        pytest.skip("bindings.ttl not present at repo root")
    return load_adapter_set(BINDINGS)


class TestRegisterAgreement:
    def test_bindings_file_loads(self, adapters):
        assert not adapters.empty

    def test_every_firmware_register_is_declared(self, adapters):
        declared = {e["property_name"]: e["address"] for e in adapters.modbus_plan()}
        for name in FIRMWARE_REGISTERS:
            assert name in declared, f"{name} missing from bindings.ttl"

    def test_addresses_match_the_firmware_header(self, adapters):
        declared = {e["property_name"]: e["address"] for e in adapters.modbus_plan()}
        for name, address in FIRMWARE_REGISTERS.items():
            assert declared[name] == address, (
                f"{name}: ontology says {declared[name]}, firmware says {address}"
            )

    def test_scaling_matches_the_firmware(self, adapters):
        for entry in adapters.modbus_plan():
            if entry["property_name"] in FIRMWARE_REGISTERS:
                assert entry["scale_factor"] == pytest.approx(1.0 / FIRMWARE_SCALING)

    def test_temperature_is_signed(self, adapters):
        entry = next(
            e for e in adapters.modbus_plan() if e["property_name"] == "temperature"
        )
        assert entry["register_type"] == "int16", (
            "temperature must be int16; uint16 turns -5.3C into 651.02C"
        )

    def test_humidity_is_unsigned(self, adapters):
        entry = next(
            e for e in adapters.modbus_plan() if e["property_name"] == "humidity"
        )
        assert entry["register_type"] == "uint16"

    def test_no_address_collisions(self, adapters):
        seen = {}
        for entry in adapters.modbus_plan():
            key = (entry["slave_id"], entry["address"])
            assert key not in seen, f"address {key} used by two properties"
            seen[key] = entry["property_name"]

    def test_data_registers_do_not_overlap_status_registers(self, adapters):
        data_addresses = {
            e["address"]
            for e in adapters.modbus_plan()
            if e["property_name"] in FIRMWARE_REGISTERS
        }
        assert not (data_addresses & set(FIRMWARE_STATUS_REGISTERS.values()))


class TestDecodingAgreement:
    def test_known_reading_decodes_correctly(self, adapters):
        readings = adapters.decode_modbus_block(1, [2610, 5620], start_address=0)
        values = {r["property_name"]: r["value"] for r in readings}
        assert values["temperature"] == pytest.approx(26.10)
        assert values["humidity"] == pytest.approx(56.20)

    def test_sub_zero_reading_decodes_correctly(self, adapters):
        readings = adapters.decode_modbus_block(1, [(-530) & 0xFFFF, 5620], 0)
        values = {r["property_name"]: r["value"] for r in readings}
        assert values["temperature"] == pytest.approx(-5.30)

    def test_generated_message_passes_the_semantic_gate(self, adapters):
        from semantic_layer.observation_gate import check_and_prepare
        from smart_factory_contracts.messages import UnifiedMessage

        messages = adapters.messages_from_modbus_block(1, [2610, 5620], 0)
        assert messages
        for message in messages:
            assert check_and_prepare(UnifiedMessage(**message)).accepted
