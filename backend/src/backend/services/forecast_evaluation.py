from __future__ import annotations

import json
import math
import os
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from analytics import trend_forecast
from analytics.thresholds import resolver
from backend.db import connection, transaction

FORECAST_HORIZON_MINUTES = 10.0
FORECAST_SAVE_INTERVAL_SECONDS = 60.0
MAX_EVALUATION_LAG_SECONDS = 30.0
FORECAST_RETENTION_DAYS = int(os.getenv("FORECAST_RETENTION_DAYS", "30"))

_EXCLUDED_PROPERTIES = {"occupancy", "light_state", "count"}
_restore_lock = threading.RLock()
_restored = False


def _utc(moment: Optional[datetime] = None) -> datetime:
    value = moment or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def restore_windows(before: Optional[datetime] = None) -> dict[str, int]:
    """Restore the latest rolling-window samples from SQLite once per process."""
    global _restored

    with _restore_lock:
        if _restored:
            return {
                "series": len(trend_forecast.tracked_series()),
                "samples": sum(
                    item["samples"] for item in trend_forecast.tracked_series()
                ),
            }

        cutoff = _utc(before).isoformat()
        with connection() as conn:
            rows = conn.execute(
                """SELECT device_id, timestamp, measurements
                   FROM sensor_data
                   WHERE timestamp < ?
                   ORDER BY timestamp DESC
                   LIMIT 10000""",
                (cutoff,),
            ).fetchall()

        buckets: dict[tuple[str, str], list[tuple[datetime, float]]] = defaultdict(list)

        for row in rows:
            try:
                observed_at = datetime.fromisoformat(row["timestamp"])
                measurements = json.loads(row["measurements"])
            except (TypeError, ValueError, json.JSONDecodeError):
                continue

            for measurement in measurements:
                property_name = str(measurement.get("type", ""))
                key = (row["device_id"], property_name)
                if not property_name or len(buckets[key]) >= trend_forecast.WINDOW_SIZE:
                    continue
                try:
                    value = float(measurement["value"])
                except (KeyError, TypeError, ValueError):
                    continue
                buckets[key].append((observed_at, value))

        for (device_id, property_name), samples in buckets.items():
            for observed_at, value in reversed(samples):
                trend_forecast.record(
                    device_id,
                    property_name,
                    value,
                    at=observed_at,
                )

        _restored = True
        return {
            "series": len(buckets),
            "samples": sum(len(values) for values in buckets.values()),
        }


def _breached(value: float, threshold: float, direction: str) -> bool:
    return value >= threshold if direction == "above" else value <= threshold


def _forecast_state(snapshot: dict[str, Any], direction: str) -> str:
    current = float(snapshot["current_value"])
    threshold = float(snapshot["threshold"])
    minutes_to = snapshot.get("minutes_to_threshold")
    significant = bool(snapshot.get("significant"))

    if _breached(current, threshold, direction):
        return "breached"
    if significant and minutes_to is not None:
        if 0 <= float(minutes_to) <= FORECAST_HORIZON_MINUTES:
            return "predicted_breach"
        if float(minutes_to) > FORECAST_HORIZON_MINUTES:
            return "watch"
    return "stable"


def _evaluate_due(
    device_id: str,
    property_name: str,
    actual_value: float,
    observed_at: datetime,
) -> None:
    observed_at = _utc(observed_at)
    observed_iso = observed_at.isoformat()

    with transaction() as conn:
        rows = conn.execute(
            """SELECT *
               FROM forecast_history
               WHERE device_id = ?
                 AND property_name = ?
                 AND status = 'pending'
                 AND target_at <= ?
               ORDER BY target_at ASC""",
            (device_id, property_name, observed_iso),
        ).fetchall()

        for row in rows:
            target_at = datetime.fromisoformat(row["target_at"])
            lag = (observed_at - _utc(target_at)).total_seconds()

            if lag > MAX_EVALUATION_LAG_SECONDS:
                conn.execute(
                    """UPDATE forecast_history
                       SET status = 'missed',
                           evaluated_at = ?
                       WHERE id = ?""",
                    (observed_iso, row["id"]),
                )
                continue

            predicted = float(row["predicted_value"])
            error = float(actual_value) - predicted
            covered = int(
                float(row["predicted_ci_low"])
                <= float(actual_value)
                <= float(row["predicted_ci_high"])
            )
            actual_breach = int(
                _breached(
                    float(actual_value),
                    float(row["threshold"]),
                    row["direction"],
                )
            )

            conn.execute(
                """UPDATE forecast_history
                   SET status = 'evaluated',
                       actual_value = ?,
                       evaluated_at = ?,
                       error = ?,
                       absolute_error = ?,
                       squared_error = ?,
                       covered = ?,
                       actual_breach = ?
                   WHERE id = ?""",
                (
                    float(actual_value),
                    observed_iso,
                    error,
                    abs(error),
                    error * error,
                    covered,
                    actual_breach,
                    row["id"],
                ),
            )


def _persist_snapshot(
    device_id: str,
    property_name: str,
    snapshot: dict[str, Any],
    direction: str,
    issued_at: datetime,
) -> Optional[str]:
    issued_at = _utc(issued_at)
    issued_iso = issued_at.isoformat()

    with transaction() as conn:
        previous = conn.execute(
            """SELECT issued_at
               FROM forecast_history
               WHERE device_id = ? AND property_name = ?
               ORDER BY issued_at DESC
               LIMIT 1""",
            (device_id, property_name),
        ).fetchone()

        if previous is not None:
            previous_at = _utc(datetime.fromisoformat(previous["issued_at"]))
            elapsed = (issued_at - previous_at).total_seconds()
            if elapsed < FORECAST_SAVE_INTERVAL_SECONDS:
                return None

        threshold = float(snapshot["threshold"])
        predicted = float(snapshot["predicted_value"])
        forecast_id = str(uuid.uuid4())
        target_at = issued_at + timedelta(minutes=FORECAST_HORIZON_MINUTES)

        conn.execute(
            """INSERT INTO forecast_history (
                   id, device_id, property_name, issued_at,
                   horizon_minutes, target_at, current_value,
                   predicted_value, predicted_ci_low, predicted_ci_high,
                   threshold, direction, state, samples, r_squared,
                   significant, status, predicted_breach
               )
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (
                forecast_id,
                device_id,
                property_name,
                issued_iso,
                FORECAST_HORIZON_MINUTES,
                target_at.isoformat(),
                float(snapshot["current_value"]),
                predicted,
                float(snapshot["predicted_ci_95"][0]),
                float(snapshot["predicted_ci_95"][1]),
                threshold,
                direction,
                _forecast_state(snapshot, direction),
                int(snapshot["samples"]),
                float(snapshot["r_squared"]),
                int(bool(snapshot["significant"])),
                int(_breached(predicted, threshold, direction)),
            ),
        )

        retention_cutoff = (
            issued_at - timedelta(days=FORECAST_RETENTION_DAYS)
        ).isoformat()
        conn.execute(
            "DELETE FROM forecast_history WHERE issued_at < ?",
            (retention_cutoff,),
        )

    return forecast_id


def observe(
    device_id: str,
    property_name: str,
    value: float,
    observed_at: Optional[datetime] = None,
) -> Optional[str]:
    """Evaluate mature forecasts, update the window, and save a new snapshot."""
    moment = _utc(observed_at)
    restore_windows(before=moment)
    _evaluate_due(device_id, property_name, float(value), moment)

    trend_forecast.record(
        device_id,
        property_name,
        float(value),
        at=moment,
    )

    threshold_spec = resolver.threshold_for(property_name)
    if threshold_spec is None or property_name in _EXCLUDED_PROPERTIES:
        return None

    threshold, direction = threshold_spec
    result = trend_forecast.forecast(
        device_id,
        property_name,
        horizon_minutes=FORECAST_HORIZON_MINUTES,
        threshold=threshold,
    ).to_dict()

    if "predicted_value" not in result:
        return None

    return _persist_snapshot(
        device_id,
        property_name,
        result,
        direction,
        moment,
    )


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {
            "evaluated": 0,
            "mae": None,
            "rmse": None,
            "bias": None,
            "normalized_mae": None,
            "normalized_rmse": None,
            "interval_coverage_95": None,
            "event_precision": None,
            "event_recall": None,
        }

    mae = sum(float(row["absolute_error"]) for row in rows) / n
    mse = sum(float(row["squared_error"]) for row in rows) / n
    bias = sum(float(row["error"]) for row in rows) / n
    coverage = sum(int(row["covered"]) for row in rows) / n
    normalized_absolute_errors = [
        float(row["absolute_error"]) / max(abs(float(row["threshold"])), 1e-9)
        for row in rows
    ]
    normalized_squared_errors = [
        value * value for value in normalized_absolute_errors
    ]
    normalized_mae = sum(normalized_absolute_errors) / n
    normalized_rmse = math.sqrt(sum(normalized_squared_errors) / n)

    true_positive = sum(
        int(row["predicted_breach"] == 1 and row["actual_breach"] == 1)
        for row in rows
    )
    false_positive = sum(
        int(row["predicted_breach"] == 1 and row["actual_breach"] == 0)
        for row in rows
    )
    false_negative = sum(
        int(row["predicted_breach"] == 0 and row["actual_breach"] == 1)
        for row in rows
    )

    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative

    return {
        "evaluated": n,
        "mae": round(mae, 4),
        "rmse": round(math.sqrt(mse), 4),
        "bias": round(bias, 4),
        "normalized_mae": round(normalized_mae, 4),
        "normalized_rmse": round(normalized_rmse, 4),
        "interval_coverage_95": round(coverage, 4),
        "event_precision": (
            round(true_positive / precision_denominator, 4)
            if precision_denominator
            else None
        ),
        "event_recall": (
            round(true_positive / recall_denominator, 4)
            if recall_denominator
            else None
        ),
    }


def quality_status(metrics: dict[str, Any]) -> str:
    evaluated = int(metrics.get("evaluated") or 0)
    if evaluated < 30:
        return "insufficient_data"

    coverage = metrics.get("interval_coverage_95")
    normalized_mae = metrics.get("normalized_mae")

    if (
        evaluated >= 100
        and coverage is not None
        and coverage >= 0.85
        and normalized_mae is not None
        and normalized_mae <= 0.10
    ):
        return "reliable"

    return "low_confidence"


def backtest_summary(
    days: int = 7,
    device_id: Optional[str] = None,
    property_name: Optional[str] = None,
) -> dict[str, Any]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conditions = ["issued_at >= ?"]
    params: list[Any] = [cutoff]

    if device_id:
        conditions.append("device_id = ?")
        params.append(device_id)
    if property_name:
        conditions.append("property_name = ?")
        params.append(property_name)

    where = " AND ".join(conditions)

    with connection() as conn:
        raw_rows = conn.execute(
            f"""SELECT *
                FROM forecast_history
                WHERE {where}
                ORDER BY issued_at DESC""",
            params,
        ).fetchall()

    rows = [dict(row) for row in raw_rows]
    evaluated = [row for row in rows if row["status"] == "evaluated"]

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in evaluated:
        grouped[(row["device_id"], row["property_name"])].append(row)

    series = []
    for (series_device, series_property), values in sorted(grouped.items()):
        metrics = _metrics(values)
        series.append(
            {
                "device_id": series_device,
                "property_name": series_property,
                **metrics,
                "model_quality": quality_status(metrics),
            }
        )

    overall = _metrics(evaluated)
    overall["mae"] = None
    overall["rmse"] = None
    overall["bias"] = None
    overall["note"] = (
        "Raw MAE, RMSE and bias are omitted across mixed measurement units; "
        "use normalized metrics or per-series results."
    )

    return {
        "window_days": days,
        "horizon_minutes": FORECAST_HORIZON_MINUTES,
        "saved": len(rows),
        "pending": sum(row["status"] == "pending" for row in rows),
        "evaluated": len(evaluated),
        "missed": sum(row["status"] == "missed" for row in rows),
        "overall": overall,
        "series": series,
    }


def forecast_quality_map(days: int = 30) -> dict[tuple[str, str], dict[str, Any]]:
    summary = backtest_summary(days=days)
    return {
        (item["device_id"], item["property_name"]): item
        for item in summary["series"]
    }


def forecast_history(
    device_id: str,
    property_name: Optional[str] = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Return persisted forecasts for one device, newest first."""
    bounded_limit = max(1, min(int(limit), 500))
    conditions = ["device_id = ?"]
    params: list[Any] = [device_id]

    if property_name:
        conditions.append("property_name = ?")
        params.append(property_name)

    where = " AND ".join(conditions)

    with connection() as conn:
        total = int(
            conn.execute(
                f"SELECT COUNT(*) FROM forecast_history WHERE {where}",
                params,
            ).fetchone()[0]
        )
        rows = conn.execute(
            f"""SELECT
                    id, device_id, property_name,
                    issued_at, target_at, horizon_minutes,
                    current_value, predicted_value,
                    predicted_ci_low, predicted_ci_high,
                    threshold, direction, state,
                    samples, r_squared, significant,
                    status, actual_value, evaluated_at,
                    predicted_breach, actual_breach
                FROM forecast_history
                WHERE {where}
                ORDER BY issued_at DESC
                LIMIT ?""",
            [*params, bounded_limit],
        ).fetchall()

    return {
        "items": [dict(row) for row in rows],
        "total": total,
    }
