


import json
import logging
import sys
from datetime import datetime, timezone
from typing import Optional

import httpx

import connectivity.models as connectivity_models
from smart_factory_contracts.messages import UnifiedMessage

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_INTERVAL = 1.0


def log_event(event: str, level: str, device_id: Optional[str] = None, **kwargs):
    entry = {
        "service": "connectivity",
        "event": event,
        "level": level,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if device_id:
        entry["device_id"] = device_id
    entry.update(kwargs)
    print(json.dumps(entry), file=sys.stderr if level == "error" else sys.stdout)


async def forward_to_backend(msg: UnifiedMessage) -> bool:
    payload = msg.model_dump(mode="json")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            
            
            
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                headers = (
                    {"X-API-Key": connectivity_models.BACKEND_API_KEY}
                    if connectivity_models.BACKEND_API_KEY
                    else None
                )
                resp = await client.post(
                    f"{connectivity_models.BACKEND_URL}/ingest/api/v1/data",
                    json=payload,
                    headers=headers,
                )
            if resp.status_code in (200, 201):
                log_event("forward_success", "info", device_id=msg.device_id)
                return True
            else:
                log_event(
                    "forward_bad_status",
                    "warning",
                    device_id=msg.device_id,
                    status=resp.status_code,
                    attempt=attempt,
                )
        except Exception as exc:
            log_event(
                "forward_error",
                "warning",
                device_id=msg.device_id,
                error=str(exc),
                attempt=attempt,
            )
        if attempt < MAX_RETRIES:
            import asyncio

            await asyncio.sleep(RETRY_INTERVAL)

    log_event("forward_failed", "error", device_id=msg.device_id, retries=MAX_RETRIES)
    return False
