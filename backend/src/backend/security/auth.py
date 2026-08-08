# API key authentication for the backend.

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

_VALID_KEY_HASHES: set[str] = set(
    filter(None, os.environ.get("API_KEYS", "").split(","))
)

_AUTH_DISABLED = len(_VALID_KEY_HASHES) == 0


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _is_valid(key: str | None) -> bool:
    if _AUTH_DISABLED:
        return True
    if key is None:
        return False
    candidate = _hash_key(key)
    return any(hmac.compare_digest(candidate, h) for h in _VALID_KEY_HASHES)


async def require_api_key(key: str | None = Depends(_API_KEY_HEADER)) -> str:
    if _AUTH_DISABLED:
        if not hasattr(require_api_key, "_warned"):
            logger.warning(
                "API_KEYS env var is not set — authentication is DISABLED. "
                "Set API_KEYS=<sha256 hash> before deploying."
            )
            require_api_key._warned = True  # type: ignore[attr-defined]
        return "unauthenticated"

    if not _is_valid(key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return key  # type: ignore[return-value]


_PUBLIC_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc"}


async def api_key_middleware(
    request: Request,
    call_next: Callable,
):
    if request.url.path in _PUBLIC_PATHS:
        return await call_next(request)

    if _AUTH_DISABLED:
        return await call_next(request)

    key = request.headers.get("X-API-Key")
    if not _is_valid(key):
        logger.warning(
            "Unauthorized request to %s from %s",
            request.url.path,
            request.client.host if request.client else "unknown",
        )
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Invalid or missing API key"},
        )

    return await call_next(request)


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
