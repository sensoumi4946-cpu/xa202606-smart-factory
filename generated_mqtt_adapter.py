TOPIC_MAP = [{'device_id': 'ESP32_001',
  'property_name': 'humidity',
  'subsystem': 'temp_humidity',
  'unit': 'percent',
  'topic': 'factory/temp_humidity/sensors/ESP32_001/humidity',
  'qos': 1,
  'scale_factor': 1.0,
  'offset': 0.0},
 {'device_id': 'ESP32_001',
  'property_name': 'temperature',
  'subsystem': 'temp_humidity',
  'unit': 'celsius',
  'topic': 'factory/temp_humidity/sensors/ESP32_001/temperature',
  'qos': 1,
  'scale_factor': 1.0,
  'offset': 0.0}]


def subscriptions():
    return [(entry["topic"], entry["qos"]) for entry in TOPIC_MAP]


def entry_for_topic(topic):
    for entry in TOPIC_MAP:
        if entry["topic"] == topic:
            return entry
    return None


def scale(entry, raw_value):
    return float(raw_value) * entry["scale_factor"] + entry["offset"]
