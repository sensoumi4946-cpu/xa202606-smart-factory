NODE_MAP = [{'device_id': 'ESP32_001',
  'property_name': 'humidity',
  'subsystem': 'temp_humidity',
  'unit': 'percent',
  'node_id': 'ns=2;s=TempHumidity.Humidity',
  'scale_factor': 1.0,
  'offset': 0.0,
  'poll_interval_ms': 2000},
 {'device_id': 'ESP32_001',
  'property_name': 'temperature',
  'subsystem': 'temp_humidity',
  'unit': 'celsius',
  'node_id': 'ns=2;s=TempHumidity.Temperature',
  'scale_factor': 1.0,
  'offset': 0.0,
  'poll_interval_ms': 2000},
 {'device_id': 'ESP32_004',
  'property_name': 'distance',
  'subsystem': 'agv',
  'unit': 'cm',
  'node_id': 'ns=2;s=distance',
  'scale_factor': 1.0,
  'offset': 0.0,
  'poll_interval_ms': 500}]


def node_ids():
    return [entry["node_id"] for entry in NODE_MAP]


def scale(entry, raw_value):
    return float(raw_value) * entry["scale_factor"] + entry["offset"]


def build_message(entry, raw_value):
    return {
        "schema_version": "v1",
        "device_id": entry["device_id"],
        "subsystem": entry["subsystem"],
        "protocol": "opcua",
        "measurements": [
            {
                "type": entry["property_name"],
                "value": scale(entry, raw_value),
                "unit": entry["unit"],
            }
        ],
    }
