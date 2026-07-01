# Connectivity-layer configuration — read from environment variables.
# MQTT_BROKER_* control the broker connection; BACKEND_URL is the
# target for forwarding UnifiedMessages after protocol normalisation.
import os

MQTT_BROKER_HOST: str = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))
BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
