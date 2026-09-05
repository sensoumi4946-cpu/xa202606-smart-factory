from __future__ import annotations

import hashlib
import hmac
import base64
import json
import logging
import os
import secrets
import time
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def validate_configuration() -> None:
    if os.getenv("HARDWARE_PROFILE", "mock").lower() != "real":
        return
    for name in ("API_KEY", "COMMAND_SIGNING_KEY"):
        value = os.getenv(name, "").strip()
        if len(value) < 32 or "change" in value.lower():
            raise RuntimeError(f"{name} must be an independent random secret of at least 32 characters")
    if os.environ["API_KEY"] == os.environ["COMMAND_SIGNING_KEY"]:
        raise RuntimeError("API_KEY and COMMAND_SIGNING_KEY must differ")


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _load_valid_hashes() -> set[str]:
    hashes = {h.strip() for h in os.environ.get("API_KEYS", "").split(",") if h.strip()}
    plain = os.environ.get("API_KEY", "").strip()
    if plain and plain != "changeme":
        hashes.add(_hash_key(plain))
    return hashes


_VALID_KEY_HASHES: set[str] = _load_valid_hashes()

_AUTH_DISABLED = len(_VALID_KEY_HASHES) == 0
SESSION_COOKIE = "factory_session"
_FALLBACK_SESSION_SECRET = secrets.token_bytes(32)


def _is_valid(key: str | None) -> bool:
    if _AUTH_DISABLED:
        return True
    if key is None:
        return False
    candidate = _hash_key(key)
    return any(hmac.compare_digest(candidate, h) for h in _VALID_KEY_HASHES)


def _session_secret() -> bytes:
    configured = os.getenv("SESSION_SIGNING_KEY", "").strip()
    if configured:
        return hashlib.sha256(configured.encode()).digest()
    if _VALID_KEY_HASHES:
        return hashlib.sha256("|".join(sorted(_VALID_KEY_HASHES)).encode()).digest()
    return _FALLBACK_SESSION_SECRET


def create_browser_session(ttl_seconds: int) -> str:
    payload = {
        "exp": int(time.time()) + ttl_seconds,
        "nonce": secrets.token_urlsafe(12),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    body = base64.urlsafe_b64encode(raw).rstrip(b"=")
    signature = hmac.new(_session_secret(), body, hashlib.sha256).digest()
    return f"{body.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def valid_browser_session(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    body_text, signature_text = token.split(".", 1)
    try:
        body = body_text.encode()
        signature = base64.urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
        expected = hmac.new(_session_secret(), body, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return False
        raw = base64.urlsafe_b64decode(body_text + "=" * (-len(body_text) % 4))
        payload = json.loads(raw)
        return isinstance(payload.get("exp"), int) and payload["exp"] > int(time.time())
    except (ValueError, TypeError, json.JSONDecodeError):
        return False


async def require_api_key(key: str | None = Depends(_API_KEY_HEADER)) -> str:
    if _AUTH_DISABLED:
        if not hasattr(require_api_key, "_warned"):
            logger.warning(
                "API_KEYS env var is not set — authentication is DISABLED. "
                "Set API_KEYS=<sha256 hash> before deploying."
            )
            require_api_key._warned = True  
        return "unauthenticated"

    if not _is_valid(key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return key  


_PUBLIC_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc", "/api/v1/security/session"}


async def api_key_middleware(
    request: Request,
    call_next: Callable,
):
    if request.method == "OPTIONS":
        return await call_next(request)

    if request.url.path in _PUBLIC_PATHS:
        return await call_next(request)

    if _AUTH_DISABLED:
        return await call_next(request)

    key = request.headers.get("X-API-Key")
    if not key and valid_browser_session(request.cookies.get(SESSION_COOKIE)):
        request.state.browser_session = True
        return await call_next(request)
    if not _is_valid(key):
        from backend.security import device_keys
        identity = device_keys.resolve_key(key) if key else None
        if identity is None:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
        request.state.device_identity = identity
        if not await _device_request_allowed(request, identity):
            return JSONResponse(status_code=403, content={"detail": "Device key does not permit this operation"})

    return await call_next(request)


async def _device_request_allowed(request: Request, identity: dict) -> bool:
    from backend.api.innovation_api import binding_registry
    from backend.store import get_control_status
    scopes = set(identity["scopes"])
    if "admin" in scopes:
        return True
    path = request.url.path
    if path == "/api/v1/security/whoami" and request.method == "GET":
        return True
    expected = binding_registry.resolve_device_id(identity["device_id"])
    def own(value):
        return isinstance(value, str) and binding_registry.resolve_device_id(value) == expected
    if request.method != "POST":
        return False
    if path in ("/ingest/api/v1/data", "/ingest/reading", "/ingest/batch") and "ingest" in scopes:
        try:
            body = await request.json()
        except ValueError:
            return False
        records = body if isinstance(body, list) else [body]
        return bool(records) and all(isinstance(r, dict) and own(r.get("device_id", r.get("sensor_id"))) for r in records)
    if "control" in scopes and path == "/api/v1/control":
        try:
            body = await request.json()
        except ValueError:
            return False
        return isinstance(body, dict) and own(body.get("device_id"))
    if "control" in scopes and path.startswith("/api/v1/control/") and path.endswith("/ack"):
        command = get_control_status(path.split("/")[-2])
        return command is not None and own(command["device_id"])
    return False


class AuditLogger:
    def __init__(self) -> None:
        self._log = logging.getLogger("audit")

    def auth_failure(self, path: str, remote_ip: str) -> None:
        self._log.warning(
            "AUTH_FAILURE path=%s remote_ip=%s ts=%s",
            path,
            remote_ip,
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    def data_write(self, sensor_id: str, triple_count: int) -> None:
        self._log.info(
            "DATA_WRITE sensor=%s triples=%d ts=%s",
            sensor_id,
            triple_count,
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    def alert_acknowledged(self, alert_id: str, by_key_hash: str) -> None:
        self._log.info(
            "ALERT_ACK alert=%s by=%s ts=%s",
            alert_id,
            by_key_hash[:8] + "...",
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )


audit = AuditLogger()
