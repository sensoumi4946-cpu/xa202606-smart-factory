# Real hardware device configuration profiles for the 5 factory subsystems
# HARDWARE_PROFILE=lab_zstu

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModbusDeviceConfig:
    host: str
    port: int
    unit_id: int
    register_map: dict[int, tuple[str, float, str]]
    poll_interval_seconds: float = 1.0


@dataclass
class OpcuaDeviceConfig:
    endpoint_url: str
    node_map: dict[str, tuple[str, str]]
    poll_interval_seconds: float = 0.5


@dataclass
class MqttDeviceConfig:
    broker_host: str
    broker_port: int
    topic_map: dict[str, tuple[str, str, str]]


@dataclass
class HardwareProfile:
    name: str
    modbus_devices: list[ModbusDeviceConfig] = field(default_factory=list)
    opcua_devices: list[OpcuaDeviceConfig] = field(default_factory=list)
    mqtt_config: MqttDeviceConfig | None = None


# Lab profile (ZSTU)

LAB_ZSTU = HardwareProfile(
    name="lab_zstu",

    modbus_devices=[

        ModbusDeviceConfig(
            host="192.168.1.101",        # mock IP
            port=502,
            unit_id=1,
            register_map={
                0x0001: ("smoke",           0.1,  "ppm"),
                0x0002: ("co",              0.1,  "ppm"),
                0x0003: ("combustible_gas", 0.1,  "ppm"),
            },
            poll_interval_seconds=1.0,
        ),
    ],

    opcua_devices=[
        # AGV obstacle avoidance — HC-SR04 ultrasonic
        OpcuaDeviceConfig(
            endpoint_url="opc.tcp://192.168.1.102:4840",   # replace
            node_map={
                "ns=2;i=1001": ("distance", "cm"),
            },
            poll_interval_seconds=0.5,
        ),
    ],

    mqtt_config=MqttDeviceConfig(
        broker_host="192.168.1.100",     # ← replace with MQTT broker IP
        broker_port=1883,
        topic_map={
            "factory/temp_humidity/dht22_01": ("sensor_dht22_01", "temperature", "celsius"),
            "factory/temp_humidity/dht22_02": ("sensor_dht22_01", "humidity",    "percent"),
            "factory/lighting/pir_01":        ("sensor_pir_01",   "occupancy",   "boolean"),
            "factory/lighting/relay_01":      ("sensor_relay_01", "light_state", "boolean"),
            "factory/counting/ir_01":         ("sensor_ir_01",    "count",       "count"),
        },
    ),
)

# Mock profile used in CI and local dev

LAB_MOCK = HardwareProfile(
    name="mock",
    modbus_devices=[
        ModbusDeviceConfig(
            host="localhost",
            port=5020,
            unit_id=1,
            register_map={
                0x0001: ("smoke",           0.1, "ppm"),
                0x0002: ("co",              0.1, "ppm"),
                0x0003: ("combustible_gas", 0.1, "ppm"),
            },
        ),
    ],
    opcua_devices=[
        OpcuaDeviceConfig(
            endpoint_url="opc.tcp://localhost:4840",
            node_map={"ns=2;i=1001": ("distance", "cm")},
        ),
    ],
    mqtt_config=MqttDeviceConfig(
        broker_host="localhost",
        broker_port=1883,
        topic_map={
            "factory/temp_humidity/dht22_01": ("sensor_dht22_01", "temperature", "celsius"),
        },
    ),
)

# Profile registry

_PROFILES: dict[str, HardwareProfile] = {
    "lab_zstu": LAB_ZSTU,
    "mock":     LAB_MOCK,
}


def get_profile(name: str = "mock") -> HardwareProfile:

    profile = _PROFILES.get(name)
    if profile is None:
        raise ValueError(f"Unknown hardware profile '{name}'. Available: {list(_PROFILES)}")
    return profile