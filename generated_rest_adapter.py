ROUTE_MAP = [
    {"device_id": "ESP32_002", "property_name": "count", "subsystem": "counting", "path": "/ingest/api/v1/data", "method": "POST", "scale_factor": 1.0, "offset": 0.0, "poll_interval_ms": 2000},
    {"device_id": "ESP32_003", "property_name": "light_state", "subsystem": "lighting", "path": "/ingest/api/v1/data", "method": "POST", "scale_factor": 1.0, "offset": 0.0, "poll_interval_ms": 2000},
    {"device_id": "ESP32_003", "property_name": "occupancy", "subsystem": "lighting", "path": "/ingest/api/v1/data", "method": "POST", "scale_factor": 1.0, "offset": 0.0, "poll_interval_ms": 2000},
]


def routes():
    return sorted({(entry["method"], entry["path"]) for entry in ROUTE_MAP})


def entries_for_device(device_id):
    return [entry for entry in ROUTE_MAP if entry["device_id"] == device_id]


def entry_for(device_id, property_name):
    for entry in ROUTE_MAP:
        if entry["device_id"] == device_id and entry["property_name"] == property_name:
            return entry
    return None


def scale(entry, raw_value):
    return float(raw_value) * entry["scale_factor"] + entry["offset"]


def build_message(entry, raw_value, unit=""):
    return {
        "schema_version": "v1",
        "device_id": entry["device_id"],
        "subsystem": entry["subsystem"],
        "protocol": "rest",
        "measurements": [
            {
                "type": entry["property_name"],
                "value": scale(entry, raw_value),
                "unit": unit,
            }
        ],
    }