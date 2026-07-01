# Backend configuration — all values sourced from environment variables
# with sensible defaults for local development. See .env.example for
# the full list.
import os

BACKEND_HOST: str = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/smart_factory.db")
MQTT_BROKER_HOST: str = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))
