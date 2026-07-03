# Connectivity-layer configuration — read from environment variables.
# MQTT_BROKER_* control the broker connection; BACKEND_URL is the
# target for forwarding UnifiedMessages after protocol normalisation.
import os

MQTT_BROKER_HOST: str = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))
BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
MODBUS_HOST: str = os.getenv("MODBUS_HOST", "localhost")
MODBUS_PORT: int = int(os.getenv("MODBUS_PORT", "1502"))
MODBUS_DEVICE_ID: str = os.getenv("MODBUS_DEVICE_ID", "sensor_mq2_01")
MODBUS_POLL_INTERVAL: float = float(os.getenv("MODBUS_POLL_INTERVAL", "2"))
