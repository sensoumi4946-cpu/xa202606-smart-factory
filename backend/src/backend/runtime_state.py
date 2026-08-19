from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from backend.db import connection, transaction

logger = logging.getLogger(__name__)

WORKER_COUNT = int(os.getenv("WEB_CONCURRENCY", os.getenv("UVICORN_WORKERS", "1")))


class MultiWorkerUnsupported(RuntimeError):
    pass


def assert_single_worker() -> None:
    if WORKER_COUNT > 1:
        raise MultiWorkerUnsupported(
            f"WEB_CONCURRENCY={WORKER_COUNT}. Analytics state (hazards, decisions, "
            "meta-model, federation sites) is shared through the runtime_state "
            "table, but the in-memory caches in front of it are per process. "
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateScope:

    def __init__(self, scope: str, max_items: int = 500) -> None:
        self.scope = scope
        self.max_items = max_items
        self._cache: dict[str, Any] = {}
        self._loaded = False
        self._lock = threading.RLock()

    def _load(self) -> None:
        if self._loaded:
            return
        with connection() as conn:
            rows = conn.execute(
                "SELECT key, value FROM runtime_state WHERE scope = ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (self.scope, self.max_items),
            ).fetchall()
        self._cache = {r["key"]: json.loads(r["value"]) for r in rows}
        self._loaded = True

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._load()
            self._cache[key] = value
        with transaction() as conn:
            conn.execute(
                "INSERT INTO runtime_state (scope, key, value, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(scope, key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                (self.scope, key, json.dumps(value, ensure_ascii=False), _now()),
            )

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            self._load()
            return self._cache.get(key, default)

    def delete(self, key: str) -> None:
        with self._lock:
            self._load()
            self._cache.pop(key, None)
        with transaction() as conn:
            conn.execute(
                "DELETE FROM runtime_state WHERE scope = ? AND key = ?",
                (self.scope, key),
            )

    def items(self) -> list[tuple[str, Any]]:
        with self._lock:
            self._load()
            return list(self._cache.items())

    def values(self) -> list[Any]:
        return [v for _, v in self.items()]

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._loaded = True
        with transaction() as conn:
            conn.execute("DELETE FROM runtime_state WHERE scope = ?", (self.scope,))

    def trim(self) -> None:
        with transaction() as conn:
            conn.execute(
                "DELETE FROM runtime_state WHERE scope = ? AND key NOT IN ("
                "SELECT key FROM runtime_state WHERE scope = ? "
                "ORDER BY key DESC LIMIT ?)",
                (self.scope, self.scope, self.max_items),
            )
        with self._lock:
            if len(self._cache) > self.max_items:
                keep = sorted(self._cache, reverse=True)[: self.max_items]
                self._cache = {k: self._cache[k] for k in keep}

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()
            self._loaded = False

    def __len__(self) -> int:
        return len(self.items())


class StateList:
    def __init__(self, scope: str, max_items: int = 200) -> None:
        self._scope = StateScope(scope, max_items)
        self.max_items = max_items
        self._counter = 0
        self._lock = threading.Lock()

    def push(self, item: dict[str, Any]) -> None:
        with self._lock:
            self._counter += 1
            key = f"{_now()}#{self._counter:06d}"
        self._scope.set(key, item)
        self._scope.trim()

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        items = sorted(self._scope.items(), key=lambda kv: kv[0], reverse=True)
        return [v for _, v in items[:limit]]

    def clear(self) -> None:
        self._scope.clear()

    def __len__(self) -> int:
        return len(self._scope)


hazards = StateList("hazards", max_items=200)
decisions = StateList("decisions", max_items=500)
predictions = StateScope("predictions", max_items=200)
agv_state = StateScope("agv", max_items=50)


def snapshot() -> dict[str, Any]:
    return {
        "worker_count": WORKER_COUNT,
        "multi_worker_supported": False,
        "scopes": {
            "hazards": len(hazards),
            "decisions": len(decisions),
            "predictions": len(predictions),
            "agv": len(agv_state),
        },
    }


def reset_all() -> None:
    hazards.clear()
    decisions.clear()
    predictions.clear()
    agv_state.clear()
