from semantic_layer.protocol_binding import decode_registers

REGISTER_MAP = [{'device_id': 'ESP32_001',
  'property_name': 'device_status',
  'subsystem': 'temp_humidity',
  'unit': 'status',
  'address': 2,
  'declared_address': 40003,
  'register_base': 40001,
  'function_code': 3,
  'count': 1,
  'register_type': 'uint16',
  'word_order': 'big',
  'byte_order': 'big',
  'scale_factor': 1.0,
  'offset': 0.0,
  'slave_id': 1,
  'poll_interval_ms': 2000},
 {'device_id': 'ESP32_001',
  'property_name': 'error_code',
  'subsystem': 'temp_humidity',
  'unit': 'status',
  'address': 3,
  'declared_address': 40004,
  'register_base': 40001,
  'function_code': 3,
  'count': 1,
  'register_type': 'uint16',
  'word_order': 'big',
  'byte_order': 'big',
  'scale_factor': 1.0,
  'offset': 0.0,
  'slave_id': 1,
  'poll_interval_ms': 2000},
 {'device_id': 'ESP32_001',
  'property_name': 'humidity',
  'subsystem': 'temp_humidity',
  'unit': 'percent',
  'address': 1,
  'declared_address': 40002,
  'register_base': 40001,
  'function_code': 3,
  'count': 1,
  'register_type': 'uint16',
  'word_order': 'big',
  'byte_order': 'big',
  'scale_factor': 0.01,
  'offset': 0.0,
  'slave_id': 1,
  'poll_interval_ms': 2000},
 {'device_id': 'ESP32_001',
  'property_name': 'sensor_status',
  'subsystem': 'temp_humidity',
  'unit': 'status',
  'address': 4,
  'declared_address': 40005,
  'register_base': 40001,
  'function_code': 3,
  'count': 1,
  'register_type': 'uint16',
  'word_order': 'big',
  'byte_order': 'big',
  'scale_factor': 1.0,
  'offset': 0.0,
  'slave_id': 1,
  'poll_interval_ms': 2000},
 {'device_id': 'ESP32_001',
  'property_name': 'temperature',
  'subsystem': 'temp_humidity',
  'unit': 'celsius',
  'address': 0,
  'declared_address': 40001,
  'register_base': 40001,
  'function_code': 3,
  'count': 1,
  'register_type': 'int16',
  'word_order': 'big',
  'byte_order': 'big',
  'scale_factor': 0.01,
  'offset': 0.0,
  'slave_id': 1,
  'poll_interval_ms': 2000},
 {'device_id': 'ESP32_005',
  'property_name': 'co',
  'subsystem': 'gas',
  'unit': 'ppm',
  'address': 6,
  'declared_address': 40007,
  'register_base': 40001,
  'function_code': 3,
  'count': 2,
  'register_type': 'float32',
  'word_order': 'big',
  'byte_order': 'big',
  'scale_factor': 1.0,
  'offset': 0.0,
  'slave_id': 2,
  'poll_interval_ms': 2000},
 {'device_id': 'ESP32_005',
  'property_name': 'combustible_gas',
  'subsystem': 'gas',
  'unit': 'ppm',
  'address': 4,
  'declared_address': 40005,
  'register_base': 40001,
  'function_code': 3,
  'count': 2,
  'register_type': 'float32',
  'word_order': 'big',
  'byte_order': 'big',
  'scale_factor': 1.0,
  'offset': 0.0,
  'slave_id': 2,
  'poll_interval_ms': 2000},
 {'device_id': 'ESP32_005',
  'property_name': 'device_status',
  'subsystem': 'gas',
  'unit': 'status',
  'address': 8,
  'declared_address': 40009,
  'register_base': 40001,
  'function_code': 3,
  'count': 1,
  'register_type': 'uint16',
  'word_order': 'big',
  'byte_order': 'big',
  'scale_factor': 1.0,
  'offset': 0.0,
  'slave_id': 2,
  'poll_interval_ms': 2000},
 {'device_id': 'ESP32_005',
  'property_name': 'smoke',
  'subsystem': 'gas',
  'unit': 'ppm',
  'address': 2,
  'declared_address': 40003,
  'register_base': 40001,
  'function_code': 3,
  'count': 2,
  'register_type': 'float32',
  'word_order': 'big',
  'byte_order': 'big',
  'scale_factor': 1.0,
  'offset': 0.0,
  'slave_id': 2,
  'poll_interval_ms': 2000}]


FUNCTION_CODE_CALLS = {
    1: "read_coils",
    2: "read_discrete_inputs",
    3: "read_holding_registers",
    4: "read_input_registers",
}


def poll_groups():
    groups = {}
    for entry in REGISTER_MAP:
        key = (entry["slave_id"], entry["function_code"], entry["poll_interval_ms"])
        groups.setdefault(key, []).append(entry)
    return groups


def read_plan():
    plan = []
    for (slave_id, function_code, interval), entries in poll_groups().items():
        addresses = [e["address"] for e in entries]
        start = min(addresses)
        span = max(a + e["count"] for a, e in zip(addresses, entries)) - start
        plan.append(
            {
                "slave_id": slave_id,
                "call": FUNCTION_CODE_CALLS[function_code],
                "address": start,
                "count": span,
                "poll_interval_ms": interval,
                "entries": entries,
            }
        )
    return plan


def decode_entry(entry, words):
    return decode_registers(
        words,
        register_type=entry["register_type"],
        word_order=entry["word_order"],
        byte_order=entry["byte_order"],
        scale_factor=entry["scale_factor"],
        offset=entry["offset"],
    )


def build_message(entry, words):
    return {
        "schema_version": "v1",
        "device_id": entry["device_id"],
        "subsystem": entry["subsystem"],
        "protocol": "modbus",
        "measurements": [
            {
                "type": entry["property_name"],
                "value": decode_entry(entry, words),
                "unit": entry["unit"],
            }
        ],
    }
