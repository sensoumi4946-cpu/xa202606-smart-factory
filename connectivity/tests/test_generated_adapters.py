# Tests for the generated-adapter runtime


from pathlib import Path

import pytest

from connectivity.generated_adapters import GeneratedAdapterSet, load_adapter_set
from semantic_layer.protocol_binding import BindingRegistry

# Mirrors modbus_register_t in the ESP32 firmware:
#   REG_TEMPERATURE = 0, REG_HUMIDITY = 1, values stored multiplied by 100
FIRMWARE_BINDINGS = """
@prefix sf:   <http://example.org/smart-factory#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

sf:binding_dht22_temperature a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresTemperature ;
    sf:transportProtocol "modbus" ;
    sf:deviceId "ESP32_001_dht22" ;
    sf:belongsToSubsystem sf:TempHumiditySubsystem ;
    sf:registerAddress 0 ; sf:registerCount 1 ; sf:registerType "int16" ;
    sf:scaleFactor "0.01"^^xsd:double ; sf:slaveId 1 ; sf:pollIntervalMs 2000 .

sf:binding_dht22_humidity a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresHumidity ;
    sf:transportProtocol "modbus" ;
    sf:deviceId "ESP32_001_dht22" ;
    sf:belongsToSubsystem sf:TempHumiditySubsystem ;
    sf:registerAddress 1 ; sf:registerCount 1 ; sf:registerType "uint16" ;
    sf:scaleFactor "0.01"^^xsd:double ; sf:slaveId 1 ; sf:pollIntervalMs 2000 .

sf:binding_hcsr04 a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresDistance ;
    sf:transportProtocol "opcua" ;
    sf:deviceId "ESP32_004_hcsr04" ;
    sf:belongsToSubsystem sf:AgvSubsystem ;
    sf:nodeId "AGV.Distance" ; sf:namespaceIndex 2 ;
    sf:scaleFactor "1.0"^^xsd:double ; sf:pollIntervalMs 500 .

sf:binding_dht22_mqtt a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresTemperature ;
    sf:transportProtocol "mqtt" ;
    sf:deviceId "ESP32_001_dht22" ;
    sf:belongsToSubsystem sf:TempHumiditySubsystem ;
    sf:mqttTopic "factory/temp_humidity/sensors/ESP32_001_dht22/temperature" ;
    sf:mqttQos 1 ; sf:scaleFactor "1.0"^^xsd:double ; sf:pollIntervalMs 2000 .

sf:binding_ir_count a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresCount ;
    sf:transportProtocol "rest" ;
    sf:deviceId "ESP32_002_ir" ;
    sf:belongsToSubsystem sf:CountingSubsystem ;
    sf:restPath "/adapter/rest/ingest" ; sf:restMethod "POST" ;
    sf:scaleFactor "1.0"^^xsd:double ; sf:pollIntervalMs 2000 .
"""


@pytest.fixture
def adapters():
    registry = BindingRegistry()
    assert registry.load_turtle(FIRMWARE_BINDINGS).accepted
    return GeneratedAdapterSet(registry)


class TestModbus:
    def test_plan_is_built_from_the_ontology(self, adapters):
        plan = adapters.modbus_plan()
        assert len(plan) == 2
        assert [e["address"] for e in plan] == [0, 1]

    def test_read_span_covers_every_register(self, adapters):
        assert adapters.modbus_read_span(1) == (0, 2)

    def test_unknown_slave_has_no_span(self, adapters):
        assert adapters.modbus_read_span(99) is None

    def test_decodes_the_firmware_scaling(self, adapters):
        readings = adapters.decode_modbus_block(1, [2610, 5620], start_address=0)
        by_name = {r["property_name"]: r["value"] for r in readings}
        assert by_name["temperature"] == pytest.approx(26.10)
        assert by_name["humidity"] == pytest.approx(56.20)

    def test_negative_temperature_decodes(self, adapters):
        readings = adapters.decode_modbus_block(1, [(-530) & 0xFFFF, 5620], 0)
        by_name = {r["property_name"]: r["value"] for r in readings}
        assert by_name["temperature"] == pytest.approx(-5.30)

    def test_humidity_never_goes_negative(self, adapters):
        readings = adapters.decode_modbus_block(1, [2610, 65535], 0)
        by_name = {r["property_name"]: r["value"] for r in readings}
        assert by_name["humidity"] > 0

    def test_units_come_from_the_property(self, adapters):
        readings = adapters.decode_modbus_block(1, [2610, 5620], 0)
        by_name = {r["property_name"]: r["unit"] for r in readings}
        assert by_name["temperature"] == "celsius"
        assert by_name["humidity"] == "percent"

    def test_short_block_is_skipped_not_crashed(self, adapters):
        readings = adapters.decode_modbus_block(1, [2610], start_address=0)
        assert len(readings) == 1
        assert readings[0]["property_name"] == "temperature"

    def test_builds_one_message_per_device(self, adapters):
        messages = adapters.messages_from_modbus_block(1, [2610, 5620], 0)
        assert len(messages) == 1
        message = messages[0]
        assert message["device_id"] == "ESP32_001_dht22"
        assert message["protocol"] == "modbus"
        assert message["subsystem"] == "temp_humidity"
        assert len(message["measurements"]) == 2

    def test_generated_message_passes_the_contract(self, adapters):
        from smart_factory_contracts.messages import UnifiedMessage

        message = adapters.messages_from_modbus_block(1, [2610, 5620], 0)[0]
        parsed = UnifiedMessage(**message)
        assert parsed.device_id == "ESP32_001_dht22"

    def test_generated_message_passes_the_semantic_gate(self, adapters):
        from semantic_layer.observation_gate import check_and_prepare
        from smart_factory_contracts.messages import UnifiedMessage

        message = adapters.messages_from_modbus_block(1, [2610, 5620], 0)[0]
        result = check_and_prepare(UnifiedMessage(**message))
        assert result.accepted


class TestOpcua:
    def test_node_ids_are_fully_qualified(self, adapters):
        nodes = adapters.opcua_nodes()
        assert nodes[0]["node_id"] == "ns=2;s=AGV.Distance"

    def test_message_built_from_node_value(self, adapters):
        message = adapters.message_from_opcua("ns=2;s=AGV.Distance", 42.0)
        assert message["device_id"] == "ESP32_004_hcsr04"
        assert message["subsystem"] == "agv"
        assert message["measurements"][0]["value"] == pytest.approx(42.0)
        assert message["measurements"][0]["unit"] == "cm"

    def test_unknown_node_returns_nothing(self, adapters):
        assert adapters.message_from_opcua("ns=2;s=Nope", 1.0) is None


class TestMqttAndRest:
    def test_subscriptions_come_from_bindings(self, adapters):
        subs = adapters.mqtt_subscriptions()
        assert ("factory/temp_humidity/sensors/ESP32_001_dht22/temperature", 1) in subs

    def test_rest_routes_come_from_bindings(self, adapters):
        routes = adapters.rest_routes()
        assert routes[0]["device_id"] == "ESP32_002_ir"
        assert routes[0]["method"] == "POST"

    def test_summary_counts_every_protocol(self, adapters):
        summary = adapters.summary()
        assert summary["modbus_registers"] == 2
        assert summary["opcua_nodes"] == 1
        assert summary["mqtt_topics"] == 1
        assert summary["rest_routes"] == 1
        assert "ESP32_001_dht22" in summary["devices"]


class TestExtension:
    def test_new_sensor_needs_no_python_change(self, adapters):
        before = len(adapters.modbus_plan())
        adapters.registry.load_turtle(
            """
@prefix sf:  <http://example.org/smart-factory#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

sf:binding_vib a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresVibration ;
    sf:transportProtocol "modbus" ;
    sf:deviceId "ESP32_005_vib" ;
    sf:belongsToSubsystem sf:VibrationSubsystem ;
    sf:registerAddress 5 ; sf:registerCount 2 ; sf:registerType "float32" ;
    sf:scaleFactor "1.0"^^xsd:double ; sf:slaveId 1 ; sf:pollIntervalMs 1000 .
"""
        )
        assert len(adapters.modbus_plan()) == before + 1
        assert adapters.modbus_read_span(1) == (0, 7)

    def test_new_sensor_decodes_immediately(self, adapters):
        from semantic_layer.protocol_binding import encode_value

        adapters.registry.load_turtle(
            """
@prefix sf:  <http://example.org/smart-factory#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

sf:binding_vib a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresVibration ;
    sf:transportProtocol "modbus" ;
    sf:deviceId "ESP32_005_vib" ;
    sf:belongsToSubsystem sf:VibrationSubsystem ;
    sf:registerAddress 5 ; sf:registerCount 2 ; sf:registerType "float32" ;
    sf:scaleFactor "1.0"^^xsd:double ; sf:slaveId 1 ; sf:pollIntervalMs 1000 .
"""
        )
        words = [2610, 5620, 0, 0, 0] + encode_value(3.25, "float32")
        readings = adapters.decode_modbus_block(1, words, start_address=0)
        by_name = {r["property_name"]: r["value"] for r in readings}
        assert by_name["vibration"] == pytest.approx(3.25, abs=1e-3)


class TestLoader:
    def test_missing_file_degrades_quietly(self, tmp_path):
        adapters = load_adapter_set(tmp_path / "nope.ttl")
        assert adapters.empty
        assert adapters.modbus_plan() == []

    def test_invalid_file_is_rejected_wholesale(self, tmp_path):
        path = tmp_path / "bad.ttl"
        path.write_text("{{{ not turtle", encoding="utf-8")
        assert load_adapter_set(path).empty

    def test_valid_file_loads(self, tmp_path):
        path = tmp_path / "ok.ttl"
        path.write_text(FIRMWARE_BINDINGS, encoding="utf-8")
        adapters = load_adapter_set(path)
        assert not adapters.empty
        assert len(adapters.modbus_plan()) == 2
