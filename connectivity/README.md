# Connectivity

The connectivity package handles protocol-specific I/O while keeping device bindings outside handwritten adapter logic.

## Supported protocols

- MQTT
- REST
- Modbus TCP
- OPC UA

## Single source of truth

Protocol/device configuration is driven by root-level `bindings.ttl`.

Examples of binding data include:

- device ID and aliases
- subsystem
- measurement/property
- unit
- MQTT topic/QoS
- Modbus address/function/scale/byte order
- OPC UA NodeId/namespace
- REST path/method
- polling interval

Generated artifacts are checked with:

```bash
python scripts/generate_adapters.py
python scripts/generate_adapters.py --check
```

## Runtime principle

Adapters normalize protocol-specific input to the shared observation contract instead of exposing raw protocol fields to backend business logic.

```text
MQTT ─┐
REST ─┤
Modbus├─→ UnifiedMessage → backend ingest
OPC UA┘
```

## Current topology

- ESP32_001: MQTT / Modbus / OPC UA bindings for temperature/humidity
- ESP32_002: REST counting
- ESP32_003: REST occupancy/light state
- ESP32_004: OPC UA AGV distance
- ESP32_005: Modbus gas observations

## OPC UA gateway

`connectivity/src/connectivity/gateways/opcua_serial.py` supports the serial-gateway route used by the AGV demonstration path.

## Test

```bash
python -m pytest connectivity/tests -q
python scripts/generate_adapters.py --check
```
