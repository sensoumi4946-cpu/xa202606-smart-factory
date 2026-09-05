# Computes Provenance Completeness

from __future__ import annotations

import asyncio
import logging
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


DEFAULT_AUDIT_DB = Path(tempfile.gettempdir()) / "semantic_provenance_audit.db"

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS prov_audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ingest_id   TEXT NOT NULL,           -- backend store row id
    device_id   TEXT NOT NULL,
    protocol    TEXT NOT NULL,
    timestamp   TEXT NOT NULL,           -- ISO-8601 UTC
    kg_written  INTEGER NOT NULL DEFAULT 0,  -- 0=failed/pending, 1=success
    written_at  TEXT,                    -- ISO-8601 UTC of successful write
    retry_count INTEGER NOT NULL DEFAULT 0,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_prov_kg ON prov_audit (kg_written);
CREATE INDEX IF NOT EXISTS idx_prov_device ON prov_audit (device_id);
"""

_RETRY_LIMIT = 5


@contextmanager
def _db_conn(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


class ProvenanceAuditLog:
    def __init__(self, db_path: Path = DEFAULT_AUDIT_DB) -> None:
        self._db = db_path
        self._init()

    def _init(self) -> None:
        with _db_conn(self._db) as conn:
            conn.executescript(_CREATE_TABLE)
            conn.commit()

    def record_attempt(
        self,
        ingest_id: str,
        device_id: str,
        protocol: str,
        observation_timestamp: datetime,
        kg_written: bool,
        error: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with _db_conn(self._db) as conn:
            conn.execute(
                "INSERT INTO prov_audit "
                "(ingest_id, device_id, protocol, timestamp, kg_written, written_at, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    ingest_id,
                    device_id,
                    protocol,
                    observation_timestamp.isoformat(),
                    int(kg_written),
                    now if kg_written else None,
                    error,
                ),
            )
            conn.commit()

    def mark_written(self, ingest_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with _db_conn(self._db) as conn:
            conn.execute(
                "UPDATE prov_audit SET kg_written = 1, written_at = ? "
                "WHERE ingest_id = ?",
                (now, ingest_id),
            )
            conn.commit()

    def increment_retry(self, ingest_id: str, error: Optional[str] = None) -> None:
        with _db_conn(self._db) as conn:
            conn.execute(
                "UPDATE prov_audit SET retry_count = retry_count + 1, error = ? "
                "WHERE ingest_id = ?",
                (error, ingest_id),
            )
            conn.commit()

    def pending_retries(self, limit: int = 50) -> list[dict]:
        with _db_conn(self._db) as conn:
            rows = conn.execute(
                "SELECT * FROM prov_audit WHERE kg_written = 0 "
                "AND retry_count < ? ORDER BY id LIMIT ?",
                (_RETRY_LIMIT, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def completeness_ratio(self, window_hours: int = 24) -> "CompletenessReport":
        cutoff = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with _db_conn(self._db) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM prov_audit WHERE timestamp >= datetime('now', ?)",
                (f"-{window_hours} hours",),
            ).fetchone()[0]
            written = conn.execute(
                "SELECT COUNT(*) FROM prov_audit WHERE kg_written=1 "
                "AND timestamp >= datetime('now', ?)",
                (f"-{window_hours} hours",),
            ).fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(*) FROM prov_audit WHERE kg_written=0 "
                "AND retry_count >= ? AND timestamp >= datetime('now', ?)",
                (_RETRY_LIMIT, f"-{window_hours} hours"),
            ).fetchone()[0]

        ratio = written / total if total > 0 else 1.0
        return CompletenessReport(
            window_hours=window_hours,
            total=total,
            written=written,
            failed_permanently=failed,
            pending_retry=total - written - failed,
            completeness_ratio=round(ratio, 4),
        )


@dataclass
class CompletenessReport:
    window_hours: int
    total: int
    written: int
    failed_permanently: int
    pending_retry: int
    completeness_ratio: float

    def to_dict(self) -> dict:
        return {
            "window_hours": self.window_hours,
            "total_ingested": self.total,
            "kg_written": self.written,
            "failed_permanently": self.failed_permanently,
            "pending_retry": self.pending_retry,
            "provenance_completeness": self.completeness_ratio,
            "passes_threshold": self.completeness_ratio >= 0.95,
        }

    def summary(self) -> str:
        return (
            f"PC={self.completeness_ratio:.1%} over {self.window_hours}h "
            f"({self.written}/{self.total} written, "
            f"{self.failed_permanently} permanently failed)"
        )


# SPARQL-backed completeness cross-check

_PROV_COUNT_QUERY = """\
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>

SELECT (COUNT(DISTINCT ?obs) AS ?count) WHERE {
  ?obs a sosa:Observation ;
       prov:generatedAtTime ?t .
  FILTER(?t >= xsd:dateTime(NOW() - "PT{hours}H"^^xsd:duration))
}
"""


async def kg_observation_count(
    fuseki_query_url: str,
    window_hours: int = 24,
) -> Optional[int]:
    query = _PROV_COUNT_QUERY.replace("{hours}", str(window_hours))
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            resp = await client.post(
                fuseki_query_url,
                content=query.encode(),
                headers={
                    "Content-Type": "application/sparql-query",
                    "Accept": "application/sparql-results+json",
                },
            )
        resp.raise_for_status()
        bindings = resp.json()["results"]["bindings"]
        if bindings:
            return int(bindings[0]["count"]["value"])
        return 0
    except (httpx.HTTPError, KeyError, ValueError):
        return None


async def retry_pending_writes(
    audit: ProvenanceAuditLog,
    write_fn,  # async callable(ingest_id: str) -> bool
    max_per_run: int = 20,
) -> dict:

    pending = audit.pending_retries(limit=max_per_run)
    stats = {"attempted": 0, "succeeded": 0, "failed": 0}

    for row in pending:
        stats["attempted"] += 1
        try:
            ok = await write_fn(row["ingest_id"])
            if ok:
                audit.mark_written(row["ingest_id"])
                stats["succeeded"] += 1
            else:
                audit.increment_retry(row["ingest_id"], error="write_fn returned False")
                stats["failed"] += 1
        except Exception as exc:
            audit.increment_retry(row["ingest_id"], error=str(exc))
            stats["failed"] += 1

    logger.info("Provenance retry run: %s", stats)
    return stats
