

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from backend.api.analytics_api import detector as _detector, correlator as _correlator, alert_history as _alert_history
    _analytics_available = True
except ImportError:
    _analytics_available = False
    logger.warning("Analytics module not available — anomaly detection disabled")


def analyse_after_ingest(
    device_id: str,
    subsystem: str,
    protocol: str,
    measurements: list[dict],
) -> list[dict]:
    
    
    if not _analytics_available:
        return []

    fired_alerts = []

    for m in measurements:
        value = m.get("value")
        property_name = m.get("type", "")
        if value is None:
            continue

        try:
            result = _detector.push_reading(
                sensor_id=device_id,
                value=float(value),
                property_name=property_name,
            )
        except Exception as exc:
            logger.warning("Anomaly detector error for %s: %s", device_id, exc)
            continue

        if result.is_anomaly:
            logger.warning(
                "Anomaly detected: %s %s=%.2f z=%.2f reason=%s",
                device_id, property_name, value,
                result.z_score or 0.0,
                result.reason,
            )
            try:
                alerts = _correlator.push_anomaly(
                    result=result,
                    subsystem=subsystem,
                    protocol=protocol,
                    property_name=property_name,
                )
                for alert in alerts:
                    record = {
                        "alert_id": alert.alert_id,
                        "triggered_at": alert.triggered_at,
                        "hypothesis": alert.hypothesis,
                        "confidence": alert.confidence,
                        "subsystems": alert.subsystems_involved,
                        "protocols": alert.protocols_involved,
                        "sources": alert.sources,
                    }
                    _alert_history.append(record)
                    fired_alerts.append(record)
                    logger.warning("Correlated alert fired: %s", alert.hypothesis)
            except Exception as exc:
                logger.warning("Correlator error: %s", exc)

    return fired_alerts