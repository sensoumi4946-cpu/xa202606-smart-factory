from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

SIGNING_KEY = os.getenv("COMMAND_SIGNING_KEY", "")
MAX_CLOCK_SKEW_S = int(os.getenv("COMMAND_MAX_SKEW_S", "30"))
NONCE_CACHE_SIZE = 4096

_seen_nonces: dict[str, float] = {}

SIGNED_FIELDS = ("command_id", "device_id", "action", "params", "issued_at", "nonce")


class SigningDisabled(RuntimeError):
    pass


def enabled() -> bool:
    return bool(SIGNING_KEY)


def canonical_payload(command: dict[str, Any]) -> str:
    params = json.dumps(
        command.get("params") or {},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return (
        "|".join(
            str(command.get(field, ""))
            for field in ("command_id", "device_id", "action")
        )
        + f"|{params}|{command.get('issued_at', '')}|{command.get('nonce', '')}"
    )


def sign(command: dict[str, Any], key: Optional[str] = None) -> str:
    secret = key if key is not None else SIGNING_KEY
    if not secret:
        raise SigningDisabled("COMMAND_SIGNING_KEY is not set")
    return hmac.new(
        secret.encode(), canonical_payload(command).encode(), hashlib.sha256
    ).hexdigest()


def attach_signature(
    command: dict[str, Any], key: Optional[str] = None
) -> dict[str, Any]:
    if "nonce" not in command:
        command["nonce"] = os.urandom(12).hex()
    command["sig_alg"] = "HMAC-SHA256-HEX"
    command["signature"] = sign(command, key)
    return command


def _prune_nonces(now: float) -> None:
    cutoff = now - MAX_CLOCK_SKEW_S * 2
    for nonce, seen in list(_seen_nonces.items()):
        if seen < cutoff:
            del _seen_nonces[nonce]


def verify(
    command: dict[str, Any],
    key: Optional[str] = None,
    now: Optional[float] = None,
) -> tuple[bool, str]:
    secret = key if key is not None else SIGNING_KEY
    if not secret:
        return False, "signing disabled"

    supplied = command.get("signature")
    if not supplied:
        return False, "missing signature"

    expected = sign(command, secret)
    if not hmac.compare_digest(expected, str(supplied)):
        return False, "signature mismatch"

    issued_at = command.get("issued_at")
    if not issued_at:
        return False, "missing issued_at"

    current = time.time() if now is None else now
    try:
        from datetime import datetime

        stamp = datetime.fromisoformat(str(issued_at))
        if stamp.tzinfo is None:
            return False, "issued_at requires timezone"
        issued = stamp.timestamp()
    except (TypeError, ValueError):
        return False, "unparseable issued_at"

    if abs(current - issued) > MAX_CLOCK_SKEW_S:
        return False, f"stale command ({abs(current - issued):.0f}s skew)"

    nonce = command.get("nonce")
    if not isinstance(nonce, str) or not nonce:
        return False, "missing nonce"
    if nonce in _seen_nonces:
        return False, "nonce replay"

    _prune_nonces(current)
    if len(_seen_nonces) >= NONCE_CACHE_SIZE:
        return False, "nonce capacity exceeded"
    _seen_nonces[str(nonce)] = current
    return True, "ok"


def reset_nonces() -> None:
    _seen_nonces.clear()
