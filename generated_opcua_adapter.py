NODE_MAP = [
    {"device_id": "esp32_02_hcsr04", "property_name": "distance", "subsystem": "agv_subsystem", "node_id": "ns=2;s=AGV.Distance", "scale_factor": 1.0, "offset": 0.0, "poll_interval_ms": 500},
]


def node_ids():
    return [entry["node_id"] for entry in NODE_MAP]


def scale(entry, raw_value):
    return float(raw_value) * entry["scale_factor"] + entry["offset"]


def build_message(entry, raw_value, unit=""):
    return {
        "schema_version": "v1",
        "device_id": entry["device_id"],
        "subsystem": entry["subsystem"],
        "protocol": "opcua",
        "measurements": [
            {
                "type": entry["property_name"],
                "value": scale(entry, raw_value),
                "unit": unit,
            }
        ],
    }
