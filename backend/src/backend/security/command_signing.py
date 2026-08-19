from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

SIGNING_KEY = os.getenv("COMMAND_SIGNING_KEY", "ce30c115aec4ca7be413779292ea725c0f323afff4ab9d70e4e946e46a6a4460")
MAX_CLOCK_SKEW_S = int(os.getenv("COMMAND_MAX_SKEW_S", "30"))
NONCE_CACHE_SIZE = 4096

_seen_nonces: dict[str, float] = {}

SIGNED_FIELDS = ("command_id", "device_id", "action", "params", "issued_at", "nonce")


class SigningDisabled(RuntimeError):
    pass


def enabled() -> bool:
    return bool(SIGNING_KEY)


def canonical_payload(command: dict[str, Any]) -> str:
    subset = {k: command.get(k) for k in SIGNED_FIELDS}
    return json.dumps(subset, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign(command: dict[str, Any], key: Optional[str] = None) -> str:
    secret = key if key is not None else SIGNING_KEY
    if not secret:
        raise SigningDisabled("COMMAND_SIGNING_KEY is not set")
    digest = hmac.new(
        secret.encode(), canonical_payload(command).encode(), hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode()


def attach_signature(command: dict[str, Any], key: Optional[str] = None) -> dict[str, Any]:
    if "nonce" not in command:
        command["nonce"] = base64.b64encode(os.urandom(9)).decode()
    command["sig_alg"] = "HMAC-SHA256"
    command["signature"] = sign(command, key)
    return command


def _prune_nonces(now: float) -> None:
    if len(_seen_nonces) <= NONCE_CACHE_SIZE:
        return
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

        issued = datetime.fromisoformat(str(issued_at)).timestamp()
    except (TypeError, ValueError):
        return False, "unparseable issued_at"

    if abs(current - issued) > MAX_CLOCK_SKEW_S:
        return False, f"stale command ({abs(current - issued):.0f}s skew)"

    nonce = command.get("nonce")
    if not nonce:
        return False, "missing nonce"
    if nonce in _seen_nonces:
        return False, "nonce replay"

    _seen_nonces[str(nonce)] = current
    _prune_nonces(current)
    return True, "ok"


def reset_nonces() -> None:
    _seen_nonces.clear()
