from __future__ import annotations

import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from queue import Empty, LifoQueue
from typing import Any, Iterator, Optional

from backend import config

logger = logging.getLogger(__name__)

POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "8"))
BUSY_TIMEOUT_MS = int(os.getenv("DB_BUSY_TIMEOUT_MS", "5000"))

SCHEMA_VERSION = 4

MIGRATIONS: dict[int, list[str]] = {
    1: [
        """CREATE TABLE IF NOT EXISTS sensor_data (
            id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            subsystem TEXT NOT NULL,
            protocol TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            measurements TEXT NOT NULL,
            raw_payload TEXT,
            ingested_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_sensor_data_device ON sensor_data(device_id)",
        "CREATE INDEX IF NOT EXISTS idx_sensor_data_timestamp ON sensor_data(timestamp DESC)",
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
        )""",
        "CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at ON alerts(triggered_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_alerts_device ON alerts(device_id)",
        """CREATE INDEX IF NOT EXISTS idx_alerts_rule_device_time
           ON alerts(rule_name, device_id, triggered_at DESC)""",
    ],
    2: [
        """CREATE TABLE IF NOT EXISTS control_commands (
            command_id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            action TEXT NOT NULL,
            params TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            dispatched_at TEXT,
            acked_at TEXT,
            result TEXT
        )""",
        """CREATE INDEX IF NOT EXISTS idx_control_device_time
           ON control_commands(device_id, created_at DESC)""",
    ],
    3: [
        """CREATE TABLE IF NOT EXISTS device_keys (
            key_id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            scopes TEXT NOT NULL,
            created_at TEXT NOT NULL,
            revoked_at TEXT,
            last_used_at TEXT,
            use_count INTEGER NOT NULL DEFAULT 0
        )""",
        "CREATE INDEX IF NOT EXISTS idx_device_keys_hash ON device_keys(key_hash)",
        "CREATE INDEX IF NOT EXISTS idx_device_keys_device ON device_keys(device_id)",
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
        )""",
        "CREATE INDEX IF NOT EXISTS idx_audit_command ON command_audit(command_id)",
        "CREATE INDEX IF NOT EXISTS idx_audit_device ON command_audit(device_id, seq DESC)",
    ],
    4: [
        """CREATE TABLE IF NOT EXISTS device_health (
            device_id TEXT PRIMARY KEY,
            device_status INTEGER,
            error_code INTEGER,
            sensor_status INTEGER,
            firmware TEXT,
            mac TEXT,
            first_seen TEXT,
            last_seen TEXT,
            message_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS runtime_state (
            scope TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (scope, key)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_runtime_scope ON runtime_state(scope, updated_at DESC)",
    ],
}


class ConnectionPool:
    def __init__(self, path: str, size: int = POOL_SIZE) -> None:
        self.path = path
        self.size = size
        self._pool: LifoQueue[sqlite3.Connection] = LifoQueue(maxsize=size)
        self._created = 0
        self._lock = threading.Lock()

    def _new_connection(self) -> sqlite3.Connection:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        conn = sqlite3.connect(
            self.path, check_same_thread=False, timeout=BUSY_TIMEOUT_MS / 1000.0
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def acquire(self) -> sqlite3.Connection:
        try:
            return self._pool.get_nowait()
        except Empty:
            pass
        with self._lock:
            if self._created < self.size:
                conn = self._new_connection()
                self._created += 1
                return conn
        return self._pool.get()

    def release(self, conn: sqlite3.Connection) -> None:
        try:
            self._pool.put_nowait(conn)
        except Exception:
            conn.close()
            with self._lock:
                self._created -= 1

    def close_all(self) -> None:
        while True:
            try:
                self._pool.get_nowait().close()
            except Empty:
                break
        with self._lock:
            self._created = 0

    def stats(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size": self.size,
            "created": self._created,
            "idle": self._pool.qsize(),
        }


_pools: dict[str, ConnectionPool] = {}
_migrated: set[str] = set()
_registry_lock = threading.RLock()


def current_path() -> str:
    return config.DATABASE_PATH


def _pool_for(path: str) -> ConnectionPool:
    with _registry_lock:
        pool = _pools.get(path)
        if pool is None:
            pool = ConnectionPool(path)
            _pools[path] = pool
        return pool


def _apply_migrations(conn: sqlite3.Connection) -> int:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current >= SCHEMA_VERSION:
        return current
    for version in range(current + 1, SCHEMA_VERSION + 1):
        for statement in MIGRATIONS.get(version, []):
            conn.execute(statement)
        conn.execute(f"PRAGMA user_version={version}")
        logger.info("applied schema migration %d", version)
    conn.commit()
    return SCHEMA_VERSION


def ensure_schema(path: Optional[str] = None) -> None:
    target = path or current_path()
    with _registry_lock:
        if target in _migrated:
            return
    pool = _pool_for(target)
    conn = pool.acquire()
    try:
        _apply_migrations(conn)
    finally:
        pool.release(conn)
    with _registry_lock:
        _migrated.add(target)


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    path = current_path()
    ensure_schema(path)
    pool = _pool_for(path)
    conn = pool.acquire()
    try:
        yield conn
    finally:
        if conn.in_transaction:
            conn.rollback()
        pool.release(conn)


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    with connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def reset_pools() -> None:
    with _registry_lock:
        for pool in _pools.values():
            pool.close_all()
        _pools.clear()
        _migrated.clear()


def schema_version(path: Optional[str] = None) -> int:
    with connection() as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


def pool_stats() -> dict[str, Any]:
    path = current_path()
    pool = _pools.get(path)
    return pool.stats() if pool else {"path": path, "size": 0, "created": 0, "idle": 0}
