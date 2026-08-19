TOPIC_MAP = [
    {"device_id": "esp32_01_dht22", "property_name": "temperature", "subsystem": "temp_humidity_subsystem", "topic": "factory/temp_humidity/sensors/esp32_01_dht22/temperature", "qos": 1, "scale_factor": 1.0, "offset": 0.0},
]


def subscriptions():
    return [(entry["topic"], entry["qos"]) for entry in TOPIC_MAP]


def entry_for_topic(topic):
    for entry in TOPIC_MAP:
        if entry["topic"] == topic:
            return entry
    return None


def scale(entry, raw_value):
    return float(raw_value) * entry["scale_factor"] + entry["offset"]
