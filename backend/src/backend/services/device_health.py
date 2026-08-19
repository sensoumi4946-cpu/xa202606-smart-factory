from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from backend.db import connection, transaction

logger = logging.getLogger(__name__)

DEVICE_STATUS = {
    0: ("normal", "正常"),
    1: ("starting", "启动中"),
    2: ("degraded", "降级运行"),
    3: ("fault", "故障"),
    4: ("maintenance", "维护中"),
}

SENSOR_STATUS = {
    0: ("ok", "传感器正常"),
    1: ("warming_up", "预热中"),
    2: ("drifting", "读数漂移"),
    3: ("disconnected", "传感器断连"),
    4: ("out_of_range", "读数超量程"),
}

ERROR_CODES = {
    0: ("none", "无故障"),
    1: ("read_timeout", "读取超时"),
    2: ("checksum", "校验错误"),
    3: ("wifi_lost", "网络断开"),
    4: ("low_voltage", "供电电压低"),
    5: ("calibration_due", "需要重新标定"),
}

SEVERITY_BY_DEVICE_STATUS = {
    0: "ok",
    1: "info",
    2: "warning",
    3: "critical",
    4: "info",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def decode_status_registers(words: list[int]) -> dict[str, Any]:
    if len(words) < 3:
        raise ValueError("status block needs three registers")

    device_status, error_code, sensor_status = (int(w) & 0xFFFF for w in words[:3])
    dev_key, dev_label = DEVICE_STATUS.get(device_status, ("unknown", "未知状态"))
    err_key, err_label = ERROR_CODES.get(error_code, ("unknown", "未知错误码"))
    sen_key, sen_label = SENSOR_STATUS.get(sensor_status, ("unknown", "未知传感器状态"))

    healthy = device_status == 0 and error_code == 0 and sensor_status == 0

    return {
        "device_status": device_status,
        "device_status_key": dev_key,
        "device_status_label": dev_label,
        "error_code": error_code,
        "error_key": err_key,
        "error_label": err_label,
        "sensor_status": sensor_status,
        "sensor_key": sen_key,
        "sensor_status_label": sen_label,
        "severity": SEVERITY_BY_DEVICE_STATUS.get(device_status, "warning"),
        "healthy": healthy,
    }


def diagnose(health: dict[str, Any], reachable: bool) -> dict[str, str]:
    if not reachable and health.get("error_key") == "wifi_lost":
        return {
            "verdict": "network",
            "label": "网络断连",
            "advice": "检查 AP 覆盖与供电，传感器本身可能正常",
        }
    if not reachable:
        return {
            "verdict": "unreachable",
            "label": "失联",
            "advice": "设备无上报，先确认供电与网络",
        }
    if health.get("sensor_key") in ("disconnected", "out_of_range"):
        return {
            "verdict": "sensor",
            "label": "传感器故障",
            "advice": "网络正常但读数异常，检查探头接线或更换传感器",
        }
    if health.get("sensor_key") == "drifting":
        return {
            "verdict": "calibration",
            "label": "读数漂移",
            "advice": "建议重新标定，MQ 系列气体传感器需定期校准",
        }
    if health.get("error_key") == "calibration_due":
        return {
            "verdict": "calibration",
            "label": "待标定",
            "advice": "已达标定周期，安排现场校准",
        }
    if health.get("error_key") == "low_voltage":
        return {
            "verdict": "power",
            "label": "供电异常",
            "advice": "检查电源与线缆压降",
        }
    if health.get("device_status_key") == "fault":
        return {
            "verdict": "device",
            "label": "设备故障",
            "advice": "设备自报故障，查看错误码明细",
        }
    if health.get("device_status_key") == "warming_up" or health.get("sensor_key") == "warming_up":
        return {
            "verdict": "warming_up",
            "label": "预热中",
            "advice": "气体传感器预热期读数不可信，通常需要数分钟",
        }
    return {"verdict": "healthy", "label": "正常", "advice": ""}


def record_health(
    device_id: str,
    status_words: Optional[list[int]] = None,
    firmware: Optional[str] = None,
    mac: Optional[str] = None,
) -> dict[str, Any]:
    decoded = decode_status_registers(status_words) if status_words else {}
    now = _now()

    with transaction() as conn:
        row = conn.execute(
            "SELECT * FROM device_health WHERE device_id = ?", (device_id,)
        ).fetchone()

        if row is None:
            conn.execute(
                """INSERT INTO device_health (
                       device_id, device_status, error_code, sensor_status,
                       firmware, mac, first_seen, last_seen, message_count, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (
                    device_id,
                    decoded.get("device_status"),
                    decoded.get("error_code"),
                    decoded.get("sensor_status"),
                    firmware,
                    mac,
                    now,
                    now,
                    now,
                ),
            )
        else:
            conn.execute(
                """UPDATE device_health SET
                       device_status = COALESCE(?, device_status),
                       error_code = COALESCE(?, error_code),
                       sensor_status = COALESCE(?, sensor_status),
                       firmware = COALESCE(?, firmware),
                       mac = COALESCE(?, mac),
                       last_seen = ?,
                       message_count = message_count + 1,
                       updated_at = ?
                   WHERE device_id = ?""",
                (
                    decoded.get("device_status"),
                    decoded.get("error_code"),
                    decoded.get("sensor_status"),
                    firmware,
                    mac,
                    now,
                    now,
                    device_id,
                ),
            )
    return decoded


def get_health(device_id: str) -> Optional[dict[str, Any]]:
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM device_health WHERE device_id = ?", (device_id,)
        ).fetchone()
    return dict(row) if row else None


def list_health() -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM device_health ORDER BY device_id"
        ).fetchall()
    return [dict(r) for r in rows]


def enrich(record: dict[str, Any], reachable: bool) -> dict[str, Any]:
    words = [
        record.get("device_status"),
        record.get("error_code"),
        record.get("sensor_status"),
    ]
    if any(w is None for w in words):
        health: dict[str, Any] = {
            "device_status_label": "待上报",
            "error_label": "待上报",
            "sensor_status_label": "待上报",
            "severity": "unknown",
            "healthy": None,
        }
    else:
        health = decode_status_registers([int(w) for w in words])

    return {
        **record,
        **health,
        "reachable": reachable,
        "diagnosis": diagnose(health, reachable),
    }
