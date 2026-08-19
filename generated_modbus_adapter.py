from semantic_layer.protocol_binding import decode_registers

REGISTER_MAP = [
    {"device_id": "esp32_02_mq2", "property_name": "co", "subsystem": "gas_subsystem", "address": 40001, "count": 1, "register_type": "uint16", "word_order": "big", "byte_order": "big", "scale_factor": 0.1, "offset": 0.0, "slave_id": 1, "poll_interval_ms": 2000},
    {"device_id": "esp32_02_mq2", "property_name": "combustible_gas", "subsystem": "gas_subsystem", "address": 40002, "count": 1, "register_type": "uint16", "word_order": "big", "byte_order": "big", "scale_factor": 0.1, "offset": 0.0, "slave_id": 1, "poll_interval_ms": 2000},
    {"device_id": "esp32_02_mq2", "property_name": "smoke", "subsystem": "gas_subsystem", "address": 40003, "count": 1, "register_type": "uint16", "word_order": "big", "byte_order": "big", "scale_factor": 0.1, "offset": 0.0, "slave_id": 1, "poll_interval_ms": 2000},
]


def poll_groups():
    groups = {}
    for entry in REGISTER_MAP:
        key = (entry["slave_id"], entry["poll_interval_ms"])
        groups.setdefault(key, []).append(entry)
    return groups


def decode_entry(entry, words):
    return decode_registers(
        words,
        register_type=entry["register_type"],
        word_order=entry["word_order"],
        byte_order=entry["byte_order"],
        scale_factor=entry["scale_factor"],
        offset=entry["offset"],
    )


def build_message(entry, words, unit=""):
    return {
        "schema_version": "v1",
        "device_id": entry["device_id"],
        "subsystem": entry["subsystem"],
        "protocol": "modbus",
        "measurements": [
            {
                "type": entry["property_name"],
                "value": decode_entry(entry, words),
                "unit": unit,
            }
        ],
    }
