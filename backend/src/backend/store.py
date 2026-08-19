# SQLite-based storage layer.
#
# Uses a single-file SQLite database with WAL journaling for concurrent
# read/write safety. The schema is designed so that replacing SQLite with
# InfluxDB / IoTDB only requires rewriting this module — no API change.
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from smart_factory_contracts.messages import UnifiedMessage
from backend import config
from backend.config import LATEST_WINDOW_MINUTES
from backend.db import connection, ensure_schema, reset_pools

# Kept so existing tests can monkeypatch backend.store.DATABASE_PATH. The
# value the pool actually uses is backend.config.DATABASE_PATH, resolved on
# every call; this name is an alias for compatibility only.
DATABASE_PATH = config.DATABASE_PATH
from backend.rules import evaluate


class _PooledConnection:
    """Adapter so existing call sites keep working.

    Every function in this module was written as
        conn = _get_connection() ... conn.close()
    Rewriting all of them at once is risky, so close() returns the
    connection to the pool instead of tearing it down. The path is resolved
    per call, which is what stops tables being created in one file and read
    from another after configuration changes.
    """

    def __init__(self):
        self._ctx = connection()
        self._conn = self._ctx.__enter__()

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        self._ctx.__exit__(None, None, None)


def _get_connection():
    return _PooledConnection()


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, decl: str
) -> None:
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init_db() -> None:
    """Create or upgrade the schema for the currently configured database."""
    ensure_schema(config.DATABASE_PATH)


def close_db() -> None:
    reset_pools()


def insert_alert(
    conn: sqlite3.Connection,
    rule_name: str,
    level: str,
    device_id: str,
    subsystem: str,
    measurement_type: str,
    value: float,
    threshold: float,
    message: str,
    source_record_id: str,
    now: datetime,
) -> Optional[str]:
    cutoff = (now - timedelta(seconds=30)).isoformat()
    existing = conn.execute(
        """SELECT id FROM alerts
           WHERE rule_name = ? AND device_id = ? AND triggered_at >= ?""",
        (rule_name, device_id, cutoff),
    ).fetchone()
    if existing:
        return None
    alert_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO alerts (id, rule_name, level, device_id, subsystem,
           measurement_type, value, threshold, message, source_record_id, triggered_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            alert_id,
            rule_name,
            level,
            device_id,
            subsystem,
            measurement_type,
            value,
            threshold,
            message,
            source_record_id,
            now.isoformat(),
        ),
    )
    return alert_id


def insert_sensor_data(msg: UnifiedMessage) -> str:
    record_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    conn = _get_connection()
    conn.execute(
        """INSERT INTO sensor_data (id, device_id, subsystem, protocol, timestamp,
           measurements, raw_payload, ingested_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            record_id,
            msg.device_id,
            msg.subsystem.value,
            msg.protocol.value,
            msg.timestamp.isoformat(),
            json.dumps([m.model_dump(mode="json") for m in msg.measurements]),
            json.dumps(msg.raw_payload) if msg.raw_payload else None,
            now.isoformat(),
        ),
    )
    for m in msg.measurements:
        for alert in evaluate(m):
            insert_alert(
                conn,
                rule_name=alert["rule_name"],
                level=alert["level"],
                device_id=msg.device_id,
                subsystem=msg.subsystem.value,
                measurement_type=alert["measurement_type"],
                value=alert["value"],
                threshold=alert["threshold"],
                message=alert["message"],
                source_record_id=record_id,
                now=now,
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
    rows = conn.execute(
        "SELECT DISTINCT device_id FROM sensor_data ORDER BY device_id"
    ).fetchall()
    conn.close()
    return [row["device_id"] for row in rows]


# Command lifecycle:
#   pending    row written, not yet on the broker
#   dispatched published to MQTT, waiting for the device
#   executed   device confirmed it did the thing
#   failed     broker unreachable, or the device reported an error
VALID_COMMAND_STATUS = ("pending", "dispatched", "executed", "failed")


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


def mark_command_dispatched(command_id: str, ok: bool) -> None:
    """Called straight after the MQTT publish attempt."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_connection()
    if ok:
        conn.execute(
            """UPDATE control_commands
               SET status = 'dispatched', dispatched_at = ?
               WHERE command_id = ? AND status = 'pending'""",
            (now, command_id),
        )
    else:
        conn.execute(
            """UPDATE control_commands
               SET status = 'failed', result = 'broker unreachable'
               WHERE command_id = ? AND status = 'pending'""",
            (command_id,),
        )
    conn.commit()
    conn.close()


def ack_control_command(
    command_id: str, success: bool, detail: str = ""
) -> Optional[dict[str, Any]]:
    """Record the device's confirmation. Returns None if the id is unknown.

    Acks are idempotent — a device that retries its POST must not flip an
    already-executed command back to something else.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_connection()
    row = conn.execute(
        "SELECT status FROM control_commands WHERE command_id = ?", (command_id,)
    ).fetchone()
    if row is None:
        conn.close()
        return None

    if row["status"] in ("executed", "failed"):
        conn.close()
        return get_control_status(command_id)

    conn.execute(
        """UPDATE control_commands
           SET status = ?, acked_at = ?, result = ?
           WHERE command_id = ?""",
        ("executed" if success else "failed", now, detail, command_id),
    )
    conn.commit()
    conn.close()
    return get_control_status(command_id)


def list_control_commands(
    device_id: Optional[str] = None, limit: int = 50
) -> list[dict[str, Any]]:
    conn = _get_connection()
    if device_id:
        rows = conn.execute(
            """SELECT * FROM control_commands WHERE device_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (device_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM control_commands ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    out = []
    for row in rows:
        r = dict(row)
        r["params"] = json.loads(r["params"])
        out.append(r)
    return out


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


def get_latest(device_id: Optional[str] = None, since: Optional[str] = None) -> list[dict[str, Any]]:
    """Return the latest measurement per (device_id, measurement_type).

    When `since` is None (default), scans the last LATEST_WINDOW_MINUTES.
    Pass an explicit ISO timestamp to override (e.g. old dates in tests).
    """
    window = since if since is not None else (
        datetime.now(timezone.utc) - timedelta(minutes=LATEST_WINDOW_MINUTES)
    ).isoformat()
    conn = _get_connection()
    if device_id:
        rows = conn.execute(
            "SELECT * FROM sensor_data WHERE device_id = ? AND timestamp >= ? ORDER BY timestamp ASC",
            (device_id, window),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sensor_data WHERE timestamp >= ? ORDER BY timestamp ASC",
            (window,),
        ).fetchall()
    conn.close()

    latest_map: dict[tuple[str, str], tuple[float, str, str]] = {}
    subsys_map: dict[str, str] = {}

    for row in rows:
        r = dict(row)
        dev = r["device_id"]
        subsys = r["subsystem"]
        ts_str = r["timestamp"].replace("Z", "+00:00")
        row_ts = datetime.fromisoformat(ts_str)
        measurements = json.loads(r["measurements"])
        subsys_map[dev] = subsys
        for m in measurements:
            key = (dev, m["type"])
            if key not in latest_map:
                latest_map[key] = (m["value"], m["unit"], row_ts.isoformat())
            else:
                _, _, exist_ts_str = latest_map[key]
                exist_ts = datetime.fromisoformat(exist_ts_str.replace("Z", "+00:00"))
                if row_ts > exist_ts:
                    latest_map[key] = (m["value"], m["unit"], row_ts.isoformat())

    device_data: dict[str, list[dict[str, Any]]] = {}
    for (dev, mtype), (val, unit, ts) in sorted(latest_map.items()):
        if dev not in device_data:
            device_data[dev] = []
        device_data[dev].append(
            {"type": mtype, "value": val, "unit": unit, "timestamp": ts}
        )

    result: list[dict[str, Any]] = []
    for dev, measurements in device_data.items():
        result.append(
            {
                "device_id": dev,
                "subsystem": subsys_map.get(dev, ""),
                "measurements": measurements,
            }
        )
    return result


def query_history(
    device_id: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    conn = _get_connection()
    conditions: list[str] = []
    params: list[Any] = []

    if device_id:
        conditions.append("device_id = ?")
        params.append(device_id)
    if since:
        conditions.append("timestamp >= ?")
        params.append(since)
    if until:
        conditions.append("timestamp <= ?")
        params.append(until)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    total = conn.execute(f"SELECT COUNT(*) FROM sensor_data{where}", params).fetchone()[
        0
    ]

    query = f"SELECT * FROM sensor_data{where} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    rows = conn.execute(query, params + [limit, offset]).fetchall()
    conn.close()

    items: list[dict[str, Any]] = []
    for row in rows:
        r = dict(row)
        r["measurements"] = json.loads(r["measurements"])
        if r["raw_payload"]:
            r["raw_payload"] = json.loads(r["raw_payload"])
        items.append(r)
    return {"items": items, "total": total}


def query_alerts(
    device_id: Optional[str] = None,
    level: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    conn = _get_connection()
    conditions: list[str] = []
    params: list[Any] = []

    if device_id:
        conditions.append("device_id = ?")
        params.append(device_id)
    if level:
        conditions.append("level = ?")
        params.append(level)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    total = conn.execute(f"SELECT COUNT(*) FROM alerts{where}", params).fetchone()[0]

    query = f"SELECT * FROM alerts{where} ORDER BY triggered_at DESC LIMIT ? OFFSET ?"
    rows = conn.execute(query, params + [limit, offset]).fetchall()
    conn.close()
    return {"items": [dict(row) for row in rows], "total": total}

def get_device_registry() -> list[dict[str, Any]]:
    conn = _get_connection()
    rows = conn.execute(
        "SELECT device_id, subsystem, protocol, timestamp FROM sensor_data ORDER BY timestamp ASC"
    ).fetchall()
    conn.close()

    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        r = dict(row)
        latest[r["device_id"]] = {
            "device_id": r["device_id"],
            "subsystem": r["subsystem"],
            "protocol": r["protocol"],
            "last_seen": r["timestamp"],
        }

    return sorted(latest.values(), key=lambda d: d["device_id"])

