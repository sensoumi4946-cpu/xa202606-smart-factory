import os

BACKEND_HOST: str = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/smart_factory.db")
PUBLIC_BACKEND_URL = os.getenv("PUBLIC_BACKEND_URL", "http://localhost:8000")
API_KEY: str   = os.getenv("API_KEY", "changeme")
HARDWARE_PROFILE  = os.getenv("HARDWARE_PROFILE",  "mock")
MQTT_BROKER_HOST: str = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))

FUSEKI_ENDPOINT: str = os.getenv("FUSEKI_ENDPOINT", "http://localhost:3030/factory/data")

FUSEKI_QUERY_URL: str = os.getenv(
    "FUSEKI_QUERY_URL", "http://localhost:3030/factory/sparql"
)

SEMANTIC_WRITE_ENABLED: bool = (
    os.getenv("SEMANTIC_WRITE_ENABLED", "true").lower() == "true"
)
LATEST_WINDOW_MINUTES: int = int(os.getenv("LATEST_WINDOW_MINUTES", "30"))
PROVENANCE_AUDIT_DB: str = os.getenv("PROVENANCE_AUDIT_DB", "data/prov_audit.db")
# e.g. "http://cell-a:3030/factory/sparql,http://cell-b:3030/factory/sparql"
FEDERATED_NODES: str = os.getenv("FEDERATED_NODES", "")