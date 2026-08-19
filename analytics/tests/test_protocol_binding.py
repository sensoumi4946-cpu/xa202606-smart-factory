import pytest

from semantic_layer.protocol_binding import (
    BindingRegistry,
    ProtocolBinding,
    decode_registers,
    encode_value,
    generate_adapter,
    generate_all,
    parse_bindings,
    validate_bindings,
)

MODBUS_TTL = """
@prefix sf:   <http://example.org/smart-factory#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

sf:binding_mq2_co a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresCo ;
    sf:transportProtocol "modbus" ;
    sf:deviceId "esp32_02_mq2" ;
    sf:belongsToSubsystem sf:GasSubsystem ;
    sf:registerAddress 40001 ;
    sf:registerCount 1 ;
    sf:registerType "uint16" ;
    sf:wordOrder "big" ;
    sf:byteOrder "big" ;
    sf:scaleFactor "0.1"^^xsd:double ;
    sf:slaveId 1 ;
    sf:pollIntervalMs 2000 .

sf:binding_mq2_gas a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresCombustibleGas ;
    sf:transportProtocol "modbus" ;
    sf:deviceId "esp32_02_mq2" ;
    sf:belongsToSubsystem sf:GasSubsystem ;
    sf:registerAddress 40002 ;
    sf:registerCount 1 ;
    sf:registerType "uint16" ;
    sf:scaleFactor "0.1"^^xsd:double ;
    sf:slaveId 1 ;
    sf:pollIntervalMs 2000 .
"""

OPCUA_TTL = """
@prefix sf:   <http://example.org/smart-factory#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

sf:binding_hcsr04 a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresDistance ;
    sf:transportProtocol "opcua" ;
    sf:deviceId "esp32_02_hcsr04" ;
    sf:belongsToSubsystem sf:AgvSubsystem ;
    sf:nodeId "AGV.Distance" ;
    sf:namespaceIndex 2 ;
    sf:scaleFactor "1.0"^^xsd:double ;
    sf:pollIntervalMs 500 .
"""

MQTT_TTL = """
@prefix sf:   <http://example.org/smart-factory#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

sf:binding_dht22_temp a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresTemperature ;
    sf:transportProtocol "mqtt" ;
    sf:deviceId "esp32_01_dht22" ;
    sf:belongsToSubsystem sf:TempHumiditySubsystem ;
    sf:mqttTopic "factory/temp_humidity/sensors/esp32_01_dht22/temperature" ;
    sf:mqttQos 1 ;
    sf:scaleFactor "1.0"^^xsd:double ;
    sf:pollIntervalMs 2000 .
"""

NO_DEVICE = """
@prefix sf:  <http://example.org/smart-factory#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

sf:binding_bad a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresCo ;
    sf:transportProtocol "modbus" ;
    sf:registerAddress 40001 .
"""

BAD_PROTOCOL = """
@prefix sf:  <http://example.org/smart-factory#> .

sf:binding_bad2 a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresCo ;
    sf:transportProtocol "carrier-pigeon" ;
    sf:deviceId "esp32_02_mq2" .
"""

FAST_POLL = """
@prefix sf:  <http://example.org/smart-factory#> .

sf:binding_bad3 a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresCo ;
    sf:transportProtocol "modbus" ;
    sf:deviceId "esp32_02_mq2" ;
    sf:pollIntervalMs 5 .
"""


class TestDecoding:
    def test_uint16_scaled(self):
        assert decode_registers([435], "uint16", scale_factor=0.1) == pytest.approx(43.5)

    def test_int16_negative(self):
        assert decode_registers([0xFFFB], "int16") == pytest.approx(-5.0)

    def test_uint32_big_word_order(self):
        assert decode_registers([0x0001, 0x0000], "uint32", "big") == 65536.0

    def test_uint32_little_word_order(self):
        assert decode_registers([0x0000, 0x0001], "uint32", "little") == 65536.0

    def test_word_order_actually_changes_result(self):
        big = decode_registers([0x1234, 0x5678], "uint32", "big")
        little = decode_registers([0x1234, 0x5678], "uint32", "little")
        assert big != little

    def test_float32_round_trip(self):
        words = encode_value(26.5, "float32")
        assert decode_registers(words, "float32") == pytest.approx(26.5, abs=1e-4)

    def test_offset_applied(self):
        assert decode_registers([100], "uint16", scale_factor=1.0, offset=-50.0) == 50.0

    def test_encode_inverts_decode(self):
        words = encode_value(43.5, "uint16", scale_factor=0.1)
        assert decode_registers(words, "uint16", scale_factor=0.1) == pytest.approx(43.5)

    def test_unknown_register_type_rejected(self):
        with pytest.raises(ValueError):
            decode_registers([1], "uint64")

    def test_too_few_words_rejected(self):
        with pytest.raises(ValueError):
            decode_registers([1], "uint32")


class TestValidation:
    def test_valid_modbus_binding(self):
        ok, violations, _ = validate_bindings(MODBUS_TTL)
        assert ok
        assert violations == []

    def test_binding_without_device_rejected(self):
        ok, violations, _ = validate_bindings(NO_DEVICE)
        assert not ok
        assert any("deviceId" in v for v in violations)

    def test_unknown_protocol_rejected(self):
        ok, violations, _ = validate_bindings(BAD_PROTOCOL)
        assert not ok
        assert any("transportProtocol" in v for v in violations)

    def test_impossible_poll_interval_rejected(self):
        ok, violations, _ = validate_bindings(FAST_POLL)
        assert not ok
        assert any("pollIntervalMs" in v for v in violations)

    def test_fragment_without_bindings_rejected(self):
        ok, violations, _ = validate_bindings("@prefix sf: <http://x#> .")
        assert not ok

    def test_broken_turtle_rejected(self):
        ok, violations, _ = validate_bindings("{{{ not turtle")
        assert not ok
        assert "parse error" in violations[0]


class TestParsing:
    def test_parses_register_map(self):
        _, _, graph = validate_bindings(MODBUS_TTL)
        bindings = parse_bindings(graph)
        assert len(bindings) == 2
        co = next(b for b in bindings if b.property_name == "co")
        assert co.register_address == 40001
        assert co.scale_factor == pytest.approx(0.1)
        assert co.slave_id == 1

    def test_parses_property_name_from_iri(self):
        _, _, graph = validate_bindings(MODBUS_TTL)
        names = {b.property_name for b in parse_bindings(graph)}
        assert names == {"co", "combustible_gas"}

    def test_parses_opcua_node(self):
        _, _, graph = validate_bindings(OPCUA_TTL)
        binding = parse_bindings(graph)[0]
        assert binding.node_id == "AGV.Distance"
        assert binding.namespace_index == 2
        assert binding.poll_interval_ms == 500

    def test_parses_mqtt_topic(self):
        _, _, graph = validate_bindings(MQTT_TTL)
        binding = parse_bindings(graph)[0]
        assert binding.topic.endswith("esp32_01_dht22/temperature")
        assert binding.qos == 1

    def test_defaults_applied_when_absent(self):
        _, _, graph = validate_bindings(OPCUA_TTL)
        binding = parse_bindings(graph)[0]
        assert binding.word_order == "big"
        assert binding.register_type == "uint16"


class TestRegistry:
    def test_starts_empty(self):
        assert len(BindingRegistry()) == 0

    def test_load_adds_bindings(self):
        reg = BindingRegistry()
        result = reg.load_turtle(MODBUS_TTL)
        assert result.accepted
        assert len(reg) == 2

    def test_invalid_load_changes_nothing(self):
        reg = BindingRegistry()
        reg.load_turtle(NO_DEVICE)
        assert len(reg) == 0

    def test_filter_by_protocol(self):
        reg = BindingRegistry()
        reg.load_turtle(MODBUS_TTL)
        reg.load_turtle(OPCUA_TTL)
        assert len(reg.for_protocol("modbus")) == 2
        assert len(reg.for_protocol("opcua")) == 1

    def test_filter_by_device(self):
        reg = BindingRegistry()
        reg.load_turtle(MODBUS_TTL)
        assert len(reg.for_device("esp32_02_mq2")) == 2

    def test_devices_listed(self):
        reg = BindingRegistry()
        reg.load_turtle(MODBUS_TTL)
        reg.load_turtle(MQTT_TTL)
        assert reg.devices() == ["esp32_01_dht22", "esp32_02_mq2"]


class TestCodeGeneration:
    def _registry(self):
        reg = BindingRegistry()
        reg.load_turtle(MODBUS_TTL)
        reg.load_turtle(OPCUA_TTL)
        reg.load_turtle(MQTT_TTL)
        return reg

    def test_modbus_adapter_is_valid_python(self):
        code = generate_adapter("modbus", self._registry().all())
        compile(code, "<generated>", "exec")

    def test_opcua_adapter_is_valid_python(self):
        code = generate_adapter("opcua", self._registry().all())
        compile(code, "<generated>", "exec")

    def test_mqtt_adapter_is_valid_python(self):
        code = generate_adapter("mqtt", self._registry().all())
        compile(code, "<generated>", "exec")

    def test_generated_modbus_adapter_runs(self):
        code = generate_adapter("modbus", self._registry().all())
        namespace: dict = {}
        exec(code, namespace)
        entry = next(
            e for e in namespace["REGISTER_MAP"] if e["property_name"] == "co"
        )
        assert namespace["decode_entry"](entry, [435]) == pytest.approx(43.5)

    def test_generated_modbus_builds_a_valid_message(self):
        code = generate_adapter("modbus", self._registry().all())
        namespace: dict = {}
        exec(code, namespace)
        entry = namespace["REGISTER_MAP"][0]
        message = namespace["build_message"](entry, [435], "ppm")
        assert message["schema_version"] == "v1"
        assert message["protocol"] == "modbus"
        assert message["device_id"] == "esp32_02_mq2"
        assert message["measurements"][0]["unit"] == "ppm"

    def test_generated_modbus_groups_polls(self):
        code = generate_adapter("modbus", self._registry().all())
        namespace: dict = {}
        exec(code, namespace)
        groups = namespace["poll_groups"]()
        assert len(groups) == 1
        assert len(next(iter(groups.values()))) == 2

    def test_generated_opcua_exposes_node_ids(self):
        code = generate_adapter("opcua", self._registry().all())
        namespace: dict = {}
        exec(code, namespace)
        assert namespace["node_ids"]() == ["ns=2;s=AGV.Distance"]

    def test_generated_mqtt_exposes_subscriptions(self):
        code = generate_adapter("mqtt", self._registry().all())
        namespace: dict = {}
        exec(code, namespace)
        topics = namespace["subscriptions"]()
        assert topics[0][1] == 1
        assert "esp32_01_dht22" in topics[0][0]

    def test_generate_all_covers_every_declared_protocol(self):
        adapters = generate_all(self._registry())
        assert set(adapters) == {"modbus", "opcua", "mqtt"}
        for code in adapters.values():
            compile(code, "<generated>", "exec")

    def test_protocol_without_bindings_raises(self):
        reg = BindingRegistry()
        reg.load_turtle(MODBUS_TTL)
        with pytest.raises(ValueError):
            generate_adapter("opcua", reg.all())

    def test_unknown_protocol_raises(self):
        with pytest.raises(ValueError):
            generate_adapter("carrier-pigeon", [])

    def test_new_device_needs_no_code_change(self):
        reg = BindingRegistry()
        reg.load_turtle(MODBUS_TTL)
        before = generate_adapter("modbus", reg.all())

        reg.load_turtle(
            """
@prefix sf:  <http://example.org/smart-factory#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

sf:binding_vib a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresVibration ;
    sf:transportProtocol "modbus" ;
    sf:deviceId "esp32_04_vib" ;
    sf:belongsToSubsystem sf:VibrationSubsystem ;
    sf:registerAddress 40010 ;
    sf:registerCount 2 ;
    sf:registerType "float32" ;
    sf:scaleFactor "1.0"^^xsd:double ;
    sf:slaveId 2 ;
    sf:pollIntervalMs 1000 .
"""
        )
        after = generate_adapter("modbus", reg.all())
        assert "esp32_04_vib" not in before
        assert "esp32_04_vib" in after
        compile(after, "<generated>", "exec")

        namespace: dict = {}
        exec(after, namespace)
        entry = next(
            e for e in namespace["REGISTER_MAP"] if e["property_name"] == "vibration"
        )
        words = encode_value(3.25, "float32")
        assert namespace["decode_entry"](entry, words) == pytest.approx(3.25, abs=1e-4)
