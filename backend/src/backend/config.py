import os
from pathlib import Path


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "bindings.ttl").exists():
            return parent
    return Path.cwd()


REPO_ROOT: Path = _repo_root()


def _load_dotenv() -> None:
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


DATA_DIR: Path = REPO_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BACKEND_HOST: str = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))
PUBLIC_BACKEND_URL: str = os.getenv("PUBLIC_BACKEND_URL", "http://localhost:8000")

API_KEY: str = os.getenv("API_KEY", "")

HARDWARE_PROFILE: str = os.getenv("HARDWARE_PROFILE", "mock")

MQTT_BROKER_HOST: str = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))

FUSEKI_ENDPOINT: str = os.getenv(
    "FUSEKI_ENDPOINT", "http://localhost:3030/factory/data"
)
FUSEKI_QUERY_URL: str = os.getenv(
    "FUSEKI_QUERY_URL", "http://localhost:3030/factory/query"
)

SEMANTIC_WRITE_ENABLED: bool = (
    os.getenv("SEMANTIC_WRITE_ENABLED", "false").lower() == "true"
)

CORS_ORIGINS: tuple[str, ...] = tuple(
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
)

LATEST_WINDOW_MINUTES: int = int(os.getenv("LATEST_WINDOW_MINUTES", "30"))

DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(DATA_DIR / "smart_factory.db"))
PROVENANCE_AUDIT_DB: str = os.getenv(
    "PROVENANCE_AUDIT_DB", str(DATA_DIR / "prov_audit.db")
)

BINDINGS_TTL: str = os.getenv("BINDINGS_TTL", str(REPO_ROOT / "bindings.ttl"))
THRESHOLDS_TTL: str = os.getenv(
    "THRESHOLDS_TTL", str(REPO_ROOT / "thresholds.ttl")
)

FEDERATED_NODES: str = os.getenv("FEDERATED_NODES", "")
