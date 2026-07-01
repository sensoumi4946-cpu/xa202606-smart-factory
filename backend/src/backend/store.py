import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from smart_factory_contracts.messages import UnifiedMessage

from backend.config import DATABASE_PATH


def _get_connection() -> sqlite3.Connection:
    db_dir = os.path.dirname(DATABASE_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = _get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sensor_data (
            id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            subsystem TEXT NOT NULL,
            protocol TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            measurements TEXT NOT NULL,
            raw_payload TEXT,
            ingested_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_sensor_data_device
        ON sensor_data(device_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_sensor_data_timestamp
        ON sensor_data(timestamp DESC)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS control_commands (
            command_id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            action TEXT NOT NULL,
            params TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def insert_sensor_data(msg: UnifiedMessage) -> str:
    record_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_connection()
    conn.execute(
        """INSERT INTO sensor_data (id, device_id, subsystem, protocol, timestamp, measurements, raw_payload, ingested_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            record_id,
            msg.device_id,
            msg.subsystem.value,
            msg.protocol.value,
            msg.timestamp.isoformat(),
            json.dumps([m.model_dump(mode="json") for m in msg.measurements]),
            json.dumps(msg.raw_payload) if msg.raw_payload else None,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return record_id


def query_sensor_data(
    device_id: Optional[str] = None,
    limit: int = 100,
    since: Optional[str] = None,
) -> list[dict[str, Any]]:
    conn = _get_connection()
    conditions: list[str] = []
    params: list[Any] = []

    if device_id:
        conditions.append("device_id = ?")
        params.append(device_id)
    if since:
        conditions.append("timestamp >= ?")
        params.append(since)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    query = f"SELECT * FROM sensor_data{where} ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    results: list[dict[str, Any]] = []
    for row in rows:
        r = dict(row)
        r["measurements"] = json.loads(r["measurements"])
        if r["raw_payload"]:
            r["raw_payload"] = json.loads(r["raw_payload"])
        results.append(r)
    return results


def get_devices() -> list[str]:
    conn = _get_connection()
    rows = conn.execute("SELECT DISTINCT device_id FROM sensor_data ORDER BY device_id").fetchall()
    conn.close()
    return [row["device_id"] for row in rows]


def insert_control_command(device_id: str, action: str, params: dict) -> str:
    command_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_connection()
    conn.execute(
        """INSERT INTO control_commands (command_id, device_id, action, params, status, created_at)
           VALUES (?, ?, ?, ?, 'pending', ?)""",
        (command_id, device_id, action, json.dumps(params), now),
    )
    conn.commit()
    conn.close()
    return command_id


def get_control_status(command_id: str) -> Optional[dict[str, Any]]:
    conn = _get_connection()
    row = conn.execute(
        "SELECT * FROM control_commands WHERE command_id = ?", (command_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    r = dict(row)
    r["params"] = json.loads(r["params"])
    return r
