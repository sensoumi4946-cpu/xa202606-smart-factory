import asyncio
import json
import os
import random
import sys
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

REST_ADAPTER_URL = os.getenv(
    "REST_ADAPTER_URL", "http://localhost:8100/adapter/rest/ingest"
)
REST_PUSH_INTERVAL = float(os.getenv("REST_PUSH_INTERVAL", "2"))


def log_json(event: str, level: str = "info", **kwargs):
    entry = {
        "service": "analytics.rest_pusher",
        "event": event,
        "level": level,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    print(json.dumps(entry), file=sys.stderr if level == "error" else sys.stdout)


def make_lighting_payload(active: Optional[bool] = None) -> dict[str, Any]:
    if active is None:
        active = random.choice([True, False])
    return {
        "device": "sensor_pir_01",
        "metrics": {
            "occupancy": "active" if active else "inactive",
            "light": "on" if active else random.choice(["on", "off"]),
        },
    }


def make_counting_payload(count: Optional[int] = None) -> dict[str, Any]:
    value = count if count is not None else random.randint(0, 200)
    return {"d": "sensor_ir_01", "v": value}


async def push_once(client: httpx.AsyncClient, url: str = REST_ADAPTER_URL) -> None:
    for payload in (make_lighting_payload(), make_counting_payload()):
        device_id = str(payload.get("device") or payload.get("d") or "")
        try:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                log_json(
                    "push_bad_status",
                    level="warning",
                    device_id=device_id,
                    status=resp.status_code,
                )
            else:
                log_json("push_success", device_id=device_id, status=resp.status_code)
        except Exception as exc:
            log_json("push_error", level="warning", device_id=device_id, error=str(exc))


async def run(
    interval: float = REST_PUSH_INTERVAL, url: str = REST_ADAPTER_URL
) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            await push_once(client, url)
            await asyncio.sleep(interval)


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
