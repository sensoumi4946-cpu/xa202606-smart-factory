from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_S = int(os.getenv("FAILSAFE_HEARTBEAT_S", "5"))
DEADMAN_TIMEOUT_S = int(os.getenv("FAILSAFE_TIMEOUT_S", "15"))


@dataclass
class FailSafeSpec:
    device_id: str
    label_zh: str
    de_energised_action: str
    de_energised_label: str
    rationale_zh: str

FAIL_SAFE_SPECS: dict[str, FailSafeSpec] = {
    "valve_gas_main": FailSafeSpec(
        device_id="valve_gas_main",
        label_zh="燃气主阀",
        de_energised_action="close",
        de_energised_label="断电即关闭",
        rationale_zh="常闭阀。平台失联时必须切断气源，泄漏比停产危险。",
    ),
    "hvac_exhaust_01": FailSafeSpec(
        device_id="hvac_exhaust_01",
        label_zh="排风机",
        de_energised_action="on",
        de_energised_label="断电继续运行",
        rationale_zh="常开回路接 UPS。火灾时停排风会加剧危险，失联时保持运行。",
    ),
    "relay_lighting_01": FailSafeSpec(
        device_id="relay_lighting_01",
        label_zh="照明继电器",
        de_energised_action="on",
        de_energised_label="断电即常亮",
        rationale_zh="失联时保持照明，便于人员疏散。",
    ),
    "agv_01": FailSafeSpec(
        device_id="agv_01",
        label_zh="AGV 小车",
        de_energised_action="stop",
        de_energised_label="断电即制动",
        rationale_zh="失去指令时立即停车，不得依赖平台判断。",
    ),
}


class HeartbeatMonitor:

    def __init__(self, timeout_s: int = DEADMAN_TIMEOUT_S) -> None:
        self.timeout_s = timeout_s
        self._last: dict[str, float] = {}

    def beat(self, device_id: str, at: Optional[float] = None) -> None:
        import time

        self._last[device_id] = time.time() if at is None else at

    def age(self, device_id: str, now: Optional[float] = None) -> Optional[float]:
        import time

        last = self._last.get(device_id)
        if last is None:
            return None
        return (time.time() if now is None else now) - last

    def expired(self, device_id: str, now: Optional[float] = None) -> bool:
        age = self.age(device_id, now)
        return age is None or age > self.timeout_s

    def status(self, now: Optional[float] = None) -> list[dict[str, Any]]:
        rows = []
        for device_id, spec in FAIL_SAFE_SPECS.items():
            age = self.age(device_id, now)
            expired = self.expired(device_id, now)
            rows.append(
                {
                    "device_id": device_id,
                    "label_zh": spec.label_zh,
                    "heartbeat_age_s": None if age is None else round(age, 1),
                    "link": "lost" if expired else "ok",
                    "de_energised_action": spec.de_energised_action,
                    "de_energised_label": spec.de_energised_label,
                    "rationale_zh": spec.rationale_zh,
                    "current_safe_state": spec.de_energised_action if expired else None,
                }
            )
        return rows

    def reset(self) -> None:
        self._last.clear()


monitor = HeartbeatMonitor()


def spec_for(device_id: str) -> Optional[FailSafeSpec]:
    return FAIL_SAFE_SPECS.get(device_id)


def heartbeat_payload(device_id: str) -> dict[str, Any]:
    spec = FAIL_SAFE_SPECS.get(device_id)
    return {
        "type": "heartbeat",
        "device_id": device_id,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "interval_s": HEARTBEAT_INTERVAL_S,
        "timeout_s": DEADMAN_TIMEOUT_S,
        "de_energised_action": spec.de_energised_action if spec else "stop",
    }
