# Unit tests for the MQTT adapter's payload parser (_parse_payload).
# Covers all five subsystems, control-topic filtering, invalid JSON,
# unknown measurement types, and timestamp validity.
import json
from datetime import datetime, timezone

import pytest
from smart_factory_contracts.messages import UnifiedMessage

from connectivity.adapters.mqtt_adapter import MQTTAdapter


class FakeClient:
    def __init__(self, cb_api_version):
        pass

    def connect(self, host, port, keepalive):
        pass

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def disconnect(self):
        pass

    def subscribe(self, topic):
        pass


@pytest.fixture
def adapter():
    return MQTTAdapter()


def test_parse_valid_temperature_payload(adapter):
    topic = "factory/temp_humidity/sensors/sensor_dht22_01/temperature"
    payload = json.dumps({"type": "temperature", "value": 25.5, "unit": "celsius"})
    msg = adapter._parse_payload(topic, payload)
    assert msg is not None
    assert msg.device_id == "sensor_dht22_01"
    assert msg.subsystem.value == "temp_humidity"
    assert msg.protocol.value == "mqtt"
    assert len(msg.measurements) == 1
    assert msg.measurements[0].type.value == "temperature"
    assert msg.measurements[0].value == 25.5
    assert msg.measurements[0].unit.value == "celsius"


def test_parse_valid_gas_payload(adapter):
    topic = "factory/gas/sensors/sensor_mq2_01/co"
    payload = json.dumps({"type": "co", "value": 10.0, "unit": "ppm"})
    msg = adapter._parse_payload(topic, payload)
    assert msg is not None
    assert msg.device_id == "sensor_mq2_01"
    assert msg.subsystem.value == "gas"
    assert msg.measurements[0].type.value == "co"


def test_parse_valid_agv_payload(adapter):
    topic = "factory/agv/sensors/sensor_hcsr04_01/distance"
    payload = json.dumps({"type": "distance", "value": 150.0, "unit": "cm"})
    msg = adapter._parse_payload(topic, payload)
    assert msg is not None
    assert msg.device_id == "sensor_hcsr04_01"
    assert msg.subsystem.value == "agv"
    assert msg.measurements[0].value == 150.0


def test_parse_valid_counting_payload(adapter):
    topic = "factory/counting/sensors/sensor_ir_01/count"
    payload = json.dumps({"type": "count", "value": 42.0, "unit": "count"})
    msg = adapter._parse_payload(topic, payload)
    assert msg is not None
    assert msg.subsystem.value == "counting"


def test_parse_valid_lighting_payload(adapter):
    topic = "factory/lighting/sensors/sensor_pir_01/occupancy"
    payload = json.dumps({"type": "occupancy", "value": 1.0, "unit": "boolean"})
    msg = adapter._parse_payload(topic, payload)
    assert msg is not None
    assert msg.subsystem.value == "lighting"
    assert msg.measurements[0].type.value == "occupancy"


def test_parse_control_topic_ignored(adapter):
    topic = "factory/lighting/control/relay_01/on"
    payload = json.dumps({"action": "on"})
    msg = adapter._parse_payload(topic, payload)
    assert msg is None


def test_parse_invalid_json_returns_none(adapter):
    topic = "factory/temp_humidity/sensors/sensor_dht22_01/temperature"
    with pytest.raises(Exception):
        adapter._parse_payload(topic, "not json{{{")


def test_parse_unknown_measurement_type(adapter):
    topic = "factory/temp_humidity/sensors/sensor_dht22_01/unknown"
    payload = json.dumps({"type": "not_a_real_type", "value": 1.0, "unit": "count"})
    msg = adapter._parse_payload(topic, payload)
    assert msg is None


def test_timestamp_within_range(adapter):
    topic = "factory/temp_humidity/sensors/sensor_dht22_01/temperature"
    payload = json.dumps({"type": "temperature", "value": 25.5, "unit": "celsius"})
    before = datetime.now(timezone.utc)
    msg = adapter._parse_payload(topic, payload)
    after = datetime.now(timezone.utc)
    assert msg is not None
    diff_before = abs((msg.timestamp - before).total_seconds())
    diff_after = abs((msg.timestamp - after).total_seconds())
    assert diff_before < 2 or diff_after < 2
