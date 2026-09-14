# XA-202606 Firmware Reference

This directory contains reference ESP32 firmware and actuator-simulation support for the five competition scenarios.

## Device mapping

| Device | Reference hardware | Scenario |
|---|---|---|
| ESP32_001 | DHT22 | temperature/humidity |
| ESP32_002 | infrared beam | goods counting |
| ESP32_003 | PIR + relay | occupancy/lighting |
| ESP32_004 | HC-SR04 | AGV distance |
| ESP32_005 | MQ-2 / MQ-7 | gas monitoring |

Protocol bindings are defined in the repository-level `bindings.ttl`. Firmware identifiers, topics, registers and protocol settings must stay consistent with that binding source.

## Important evidence boundary

Reference firmware being present in the repository is not equivalent to:

- successful compilation on every target board;
- calibrated sensor accuracy;
- production wiring validation;
- 24/48 h physical endurance;
- physical actuator acceptance.

Competition evidence should come from the retained system-test records rather than from source-code existence alone.

## Simulator

`firmware/sim/actuator_agent.py` supports control-path simulation and testing. A simulator ACK is not evidence of a real valve, fan, AGV or relay physically moving.

## Tests

```bash
cd firmware
python -m pytest tests -q
```
