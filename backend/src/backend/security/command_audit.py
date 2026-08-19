# Audit log for every control command

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from backend import config

GENESIS_HASH = "0" * 64

OUTCOME_ISSUED = "issued"
OUTCOME_DISPATCHED = "dispatched"
OUTCOME_EXECUTED = "executed"
OUTCOME_FAILED = "failed"
OUTCOME_DENIED = "denied"


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_audit_log() -> None:
    conn = _connection()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS command_audit (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at TEXT NOT NULL,
            command_id TEXT,
            device_id TEXT NOT NULL,
            action TEXT NOT NULL,
            params TEXT NOT NULL DEFAULT '{}',
            actor TEXT NOT NULL,
            actor_key_id TEXT,
            source_ip TEXT,
            outcome TEXT NOT NULL,
            detail TEXT,
            prev_hash TEXT NOT NULL,
            entry_hash TEXT NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_command ON command_audit(command_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_device ON command_audit(device_id, seq DESC)"
    )
    conn.commit()
    conn.close()


def _compute_hash(payload: dict[str, Any], prev_hash: str) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + canonical).encode()).hexdigest()


def _latest_hash(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT entry_hash FROM command_audit ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    return row["entry_hash"] if row else GENESIS_HASH


def record(
    device_id: str,
    action: str,
    outcome: str,
    actor: str = "unknown",
    command_id: Optional[str] = None,
    params: Optional[dict] = None,
    actor_key_id: Optional[str] = None,
    source_ip: Optional[str] = None,
    detail: Optional[str] = None,
) -> dict[str, Any]:
    recorded_at = datetime.now(timezone.utc).isoformat()
    params = params or {}

    conn = _connection()
    prev_hash = _latest_hash(conn)

    payload = {
        "recorded_at": recorded_at,
        "command_id": command_id,
        "device_id": device_id,
        "action": action,
        "params": params,
        "actor": actor,
        "actor_key_id": actor_key_id,
        "source_ip": source_ip,
        "outcome": outcome,
        "detail": detail,
    }
    entry_hash = _compute_hash(payload, prev_hash)

    cur = conn.execute(
        """INSERT INTO command_audit (
               recorded_at, command_id, device_id, action, params, actor,
               actor_key_id, source_ip, outcome, detail, prev_hash, entry_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            recorded_at,
            command_id,
            device_id,
            action,
            json.dumps(params, sort_keys=True),
            actor,
            actor_key_id,
            source_ip,
            outcome,
            detail,
            prev_hash,
            entry_hash,
        ),
    )
    conn.commit()
    seq = cur.lastrowid
    conn.close()

    return {"seq": seq, "entry_hash": entry_hash, "prev_hash": prev_hash}


def verify_chain() -> dict[str, Any]:
    """Recompute every hash. Reports the first row that does not match."""
    conn = _connection()
    rows = conn.execute("SELECT * FROM command_audit ORDER BY seq ASC").fetchall()
    conn.close()

    expected_prev = GENESIS_HASH
    for row in rows:
        if row["prev_hash"] != expected_prev:
            return {
                "valid": False,
                "entries": len(rows),
                "broken_at_seq": row["seq"],
                "reason": "prev_hash does not match the preceding entry — a row was deleted or reordered",
            }

        payload = {
            "recorded_at": row["recorded_at"],
            "command_id": row["command_id"],
            "device_id": row["device_id"],
            "action": row["action"],
            "params": json.loads(row["params"]),
            "actor": row["actor"],
            "actor_key_id": row["actor_key_id"],
            "source_ip": row["source_ip"],
            "outcome": row["outcome"],
            "detail": row["detail"],
        }
        if _compute_hash(payload, row["prev_hash"]) != row["entry_hash"]:
            return {
                "valid": False,
                "entries": len(rows),
                "broken_at_seq": row["seq"],
                "reason": "entry contents were modified after it was written",
            }
        expected_prev = row["entry_hash"]

    return {"valid": True, "entries": len(rows), "head_hash": expected_prev}


def query(
    device_id: Optional[str] = None,
    command_id: Optional[str] = None,
    actor: Optional[str] = None,
    outcome: Optional[str] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses, args = [], []
    if device_id:
        clauses.append("device_id = ?")
        args.append(device_id)
    if command_id:
        clauses.append("command_id = ?")
        args.append(command_id)
    if actor:
        clauses.append("actor = ?")
        args.append(actor)
    if outcome:
        clauses.append("outcome = ?")
        args.append(outcome)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    args.append(limit)

    conn = _connection()
    rows = conn.execute(
        f"SELECT * FROM command_audit {where} ORDER BY seq DESC LIMIT ?", args
    ).fetchall()
    conn.close()

    out = []
    for r in rows:
        d = dict(r)
        d["params"] = json.loads(d["params"])
        out.append(d)
    return out
