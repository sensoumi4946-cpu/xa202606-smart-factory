# SQLite-based storage layer.
#
# This is the Phase 1 persistence backend. It uses a single-file SQLite
# database with WAL journaling for concurrent read/write safety.
# The schema is designed so that replacing SQLite with InfluxDB / IoTDB
# in later phases only requires rewriting this module — no API change.
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from smart_factory_contracts.messages import UnifiedMessage

from backend.config import DATABASE_PATH
from backend.rules import evaluate


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
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sensor_data (
            id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            subsystem TEXT NOT NULL,
            protocol TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            measurements TEXT NOT NULL,
            raw_payload TEXT,
            ingested_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_sensor_data_device
        ON sensor_data(device_id)"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_sensor_data_timestamp
        ON sensor_data(timestamp DESC)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS control_commands (
            command_id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            action TEXT NOT NULL,
            params TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS alerts (
            id TEXT PRIMARY KEY,
            rule_name TEXT NOT NULL,
            level TEXT NOT NULL,
            device_id TEXT NOT NULL,
            subsystem TEXT NOT NULL,
            measurement_type TEXT NOT NULL,
            value REAL NOT NULL,
            threshold REAL NOT NULL,
            message TEXT NOT NULL,
            source_record_id TEXT NOT NULL,
            triggered_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at ON alerts(triggered_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_alerts_device ON alerts(device_id)"
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_alerts_rule_device_time
        ON alerts(rule_name, device_id, triggered_at DESC)"""
    )
    conn.commit()
    conn.close()


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


def get_latest(device_id: Optional[str] = None) -> list[dict[str, Any]]:
    conn = _get_connection()
    if device_id:
        rows = conn.execute(
            "SELECT * FROM sensor_data WHERE device_id = ? ORDER BY timestamp ASC",
            (device_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sensor_data ORDER BY timestamp ASC"
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
                exist_ts = datetime.fromisoformat(
                    exist_ts_str.replace("Z", "+00:00")
                )
                if row_ts > exist_ts:
                    latest_map[key] = (m["value"], m["unit"], row_ts.isoformat())

    device_data: dict[str, list[dict[str, Any]]] = {}
    for (dev, mtype), (val, unit, ts) in sorted(latest_map.items()):
        if dev not in device_data:
            device_data[dev] = []
        device_data[dev].append({"type": mtype, "value": val, "unit": unit, "timestamp": ts})

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
    total = conn.execute(f"SELECT COUNT(*) FROM sensor_data{where}", params).fetchone()[0]

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
