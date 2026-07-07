# Structured JSON-Lines logging for the backend.
#
# Emits one JSON object per line to stdout (or stderr for errors) so
# container log collectors can parse events without a heavier framework.
# Mirrors the connectivity log_event shape for a consistent log schema
# across services.
import json
import sys
from datetime import datetime, timezone
from typing import Optional


def log_json(
    event: str, level: str = "info", device_id: Optional[str] = None, **kwargs
):
    entry = {
        "service": "backend",
        "event": event,
        "level": level,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if device_id is not None:
        entry["device_id"] = device_id
    entry.update(kwargs)
    stream = sys.stderr if level == "error" else sys.stdout
    print(json.dumps(entry), file=stream)
