

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from backend import config

SCOPE_INGEST = "ingest"
SCOPE_CONTROL = "control"
SCOPE_ADMIN = "admin"
VALID_SCOPES = (SCOPE_INGEST, SCOPE_CONTROL, SCOPE_ADMIN)

KEY_PREFIX = "xa"


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_key_store() -> None:
    conn = _connection()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS device_keys (
            key_id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            scopes TEXT NOT NULL,
            created_at TEXT NOT NULL,
            revoked_at TEXT,
            last_used_at TEXT,
            use_count INTEGER NOT NULL DEFAULT 0
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_device_keys_hash ON device_keys(key_hash)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_device_keys_device ON device_keys(device_id)"
    )
    conn.commit()
    conn.close()


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def enroll_device(
    device_id: str, scopes: Optional[list[str]] = None
) -> dict[str, Any]:
    pass
    scopes = scopes or [SCOPE_INGEST]
    for s in scopes:
        if s not in VALID_SCOPES:
            raise ValueError(f"unknown scope '{s}', valid: {VALID_SCOPES}")

    raw_key = f"{KEY_PREFIX}_{device_id}_{secrets.token_urlsafe(32)}"
    key_id = secrets.token_hex(8)

    conn = _connection()
    conn.execute(
        """INSERT INTO device_keys (key_id, device_id, key_hash, scopes, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (key_id, device_id, hash_key(raw_key), ",".join(scopes), _now()),
    )
    conn.commit()
    conn.close()

    return {
        "key_id": key_id,
        "device_id": device_id,
        "api_key": raw_key,
        "scopes": scopes,
        "warning": "This key is shown once. Store it on the device now.",
    }


def resolve_key(raw_key: str) -> Optional[dict[str, Any]]:
    
    if not raw_key:
        return None

    candidate = hash_key(raw_key)
    conn = _connection()
    rows = conn.execute(
        "SELECT * FROM device_keys WHERE revoked_at IS NULL"
    ).fetchall()

    matched = None
    for row in rows:
        if hmac.compare_digest(candidate, row["key_hash"]):
            matched = row

    if matched is None:
        conn.close()
        return None

    conn.execute(
        """UPDATE device_keys SET last_used_at = ?, use_count = use_count + 1
           WHERE key_id = ?""",
        (_now(), matched["key_id"]),
    )
    conn.commit()
    conn.close()

    return {
        "key_id": matched["key_id"],
        "device_id": matched["device_id"],
        "scopes": matched["scopes"].split(","),
    }


def has_scope(identity: Optional[dict[str, Any]], scope: str) -> bool:
    if identity is None:
        return False
    scopes = identity.get("scopes", [])
    return scope in scopes or SCOPE_ADMIN in scopes


def revoke_key(key_id: str) -> bool:
    conn = _connection()
    cur = conn.execute(
        "UPDATE device_keys SET revoked_at = ? WHERE key_id = ? AND revoked_at IS NULL",
        (_now(), key_id),
    )
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


def revoke_device(device_id: str) -> int:
    conn = _connection()
    cur = conn.execute(
        """UPDATE device_keys SET revoked_at = ?
           WHERE device_id = ? AND revoked_at IS NULL""",
        (_now(), device_id),
    )
    conn.commit()
    count = cur.rowcount
    conn.close()
    return count


def rotate_key(key_id: str) -> Optional[dict[str, Any]]:
    conn = _connection()
    row = conn.execute(
        "SELECT device_id, scopes FROM device_keys WHERE key_id = ?", (key_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    revoke_key(key_id)
    return enroll_device(row["device_id"], row["scopes"].split(","))


def list_keys(device_id: Optional[str] = None) -> list[dict[str, Any]]:
    conn = _connection()
    if device_id:
        rows = conn.execute(
            "SELECT * FROM device_keys WHERE device_id = ? ORDER BY created_at DESC",
            (device_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM device_keys ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [
        {
            "key_id": r["key_id"],
            "device_id": r["device_id"],
            "scopes": r["scopes"].split(","),
            "created_at": r["created_at"],
            "revoked_at": r["revoked_at"],
            "last_used_at": r["last_used_at"],
            "use_count": r["use_count"],
            "active": r["revoked_at"] is None,
        }
        for r in rows
    ]
