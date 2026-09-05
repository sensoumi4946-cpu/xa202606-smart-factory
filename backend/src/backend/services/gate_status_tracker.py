import threading
from datetime import datetime, timezone
from typing import Optional

_lock = threading.Lock()
_state = {
    "status": None,
    "checked_at": None,
    "last_device": None,
    "reason": None,
    "passed_count": 0,
    "rejected_count": 0,
}


def record(accepted: bool, device_id: str, reason: Optional[str] = None) -> None:
    with _lock:
        _state["status"] = "passed" if accepted else "rejected"
        _state["checked_at"] = datetime.now(timezone.utc).isoformat()
        _state["last_device"] = device_id
        _state["reason"] = reason
        if accepted:
            _state["passed_count"] += 1
        else:
            _state["rejected_count"] += 1


def snapshot() -> dict:
    with _lock:
        return dict(_state)


def reset() -> None:
    """Restore the process-wide tracker to its initial state.

    Besides making tests independent, this is useful for an operator-initiated
    reset after a maintenance window without replacing the tracker object.
    """
    with _lock:
        _state.update(
            status=None,
            checked_at=None,
            last_device=None,
            reason=None,
            passed_count=0,
            rejected_count=0,
        )
