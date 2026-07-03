# Connectivity-layer configuration — read from environment variables.
# MQTT_BROKER_* control the broker connection; BACKEND_URL is the
# target for forwarding UnifiedMessages after protocol normalisation.
import os

MQTT_BROKER_HOST: str = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))
BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
OPCUA_ENDPOINT: str = os.getenv("OPCUA_ENDPOINT", "opc.tcp://localhost:4840/")
OPCUA_DEVICE_ID: str = os.getenv("OPCUA_DEVICE_ID", "sensor_hcsr04_01")
OPCUA_DISTANCE_NODE_ID: str = os.getenv("OPCUA_DISTANCE_NODE_ID", "ns=2;s=distance")
