# retries failed Fuseki writes every N seconds

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def retry_loop(
    audit,                          # ProvenanceAuditLog instance
    fuseki_data_endpoint: str,
    interval_seconds: float = 60.0,
    max_per_run: int = 20,
) -> None:
    
    logger.info("Provenance retry service started (interval=%.0fs)", interval_seconds)

    while True:
        await asyncio.sleep(interval_seconds)
        try:
            pending = audit.pending_retries(limit=max_per_run)
            if not pending:
                continue

            logger.info("Retry run: %d pending Fuseki writes", len(pending))

            from backend.store import query_sensor_data
            from smart_factory_contracts.messages import UnifiedMessage
            from semantic_layer.fuseki import write_to_fuseki
            import json

            success, failed = 0, 0
            for row in pending:
                ingest_id = row["ingest_id"]
                device_id  = row["device_id"]
                try:
                    records = query_sensor_data(device_id=device_id, limit=1)
                    if not records:
                        audit.increment_retry(ingest_id, error="record not found")
                        failed += 1
                        continue

                    rec = records[0]
                    from smart_factory_contracts.messages import (
                        Measurement, MeasurementType, Protocol, Subsystem, Unit,
                    )
                    from datetime import datetime, timezone

                    measurements_raw = rec["measurements"]
                    measurements = []
                    for m in measurements_raw:
                        try:
                            measurements.append(Measurement(
                                type=MeasurementType(m["type"]),
                                value=float(m["value"]),
                                unit=Unit(m["unit"]),
                            ))
                        except Exception:
                            continue

                    if not measurements:
                        audit.increment_retry(ingest_id, error="no valid measurements")
                        failed += 1
                        continue

                    msg = UnifiedMessage(
                        schema_version="v1",
                        device_id=rec["device_id"],
                        subsystem=Subsystem(rec["subsystem"]),
                        protocol=Protocol(rec["protocol"]),
                        timestamp=datetime.now(timezone.utc),
                        measurements=measurements,
                    )

                    ok = await write_to_fuseki(msg, fuseki_data_endpoint)
                    if ok:
                        audit.mark_written(ingest_id)
                        success += 1
                    else:
                        audit.increment_retry(ingest_id, error="Fuseki returned non-2xx")
                        failed += 1

                except Exception as exc:
                    audit.increment_retry(ingest_id, error=str(exc))
                    failed += 1

            logger.info("Retry run complete: %d succeeded, %d failed", success, failed)

        except Exception as exc:
            logger.error("Retry service loop error: %s", exc, exc_info=True)