import os

MQTT_BROKER_HOST: str = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))
BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
BACKEND_API_KEY: str = os.getenv("API_KEY", "")
MODBUS_HOST: str = os.getenv("MODBUS_HOST", "localhost")
MODBUS_PORT: int = int(os.getenv("MODBUS_PORT", "1502"))
MODBUS_POLL_INTERVAL: float = float(os.getenv("MODBUS_POLL_INTERVAL", "2"))
RECONNECT_INTERVAL: float = float(os.getenv("RECONNECT_INTERVAL", "5"))
BINDINGS_TTL: str = os.getenv("BINDINGS_TTL", "bindings.ttl")
REST_ADAPTER_PORT: int = int(os.getenv("REST_ADAPTER_PORT", "8100"))
OPCUA_ENDPOINT: str = os.getenv("OPCUA_ENDPOINT", "opc.tcp://localhost:4840/")
OPCUA_SECURITY_STRING: str = os.getenv("OPCUA_SECURITY_STRING", "")
OPCUA_USERNAME: str = os.getenv("OPCUA_USERNAME", "")
OPCUA_PASSWORD: str = os.getenv("OPCUA_PASSWORD", "")
OPCUA_USER_CERTIFICATE: str = os.getenv("OPCUA_USER_CERTIFICATE", "")
OPCUA_USER_PRIVATE_KEY: str = os.getenv("OPCUA_USER_PRIVATE_KEY", "")
OPCUA_USER_PRIVATE_KEY_PASSWORD: str = os.getenv(
    "OPCUA_USER_PRIVATE_KEY_PASSWORD", ""
)
