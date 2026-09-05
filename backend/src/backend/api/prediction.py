from __future__ import annotations

import logging
import time
import os
from typing import Any, Optional

from fastapi import APIRouter, Query

from analytics.agv_guard import AgvGuard
from analytics.fault_predictor import FaultPredictor
from analytics.hazard_reasoner import HazardReasoner
from analytics.decision_provenance import ledger
from analytics.safety_controller import SafetyController
from semantic_layer.meta_model import registry as meta_registry

logger = logging.getLogger(__name__)

router = APIRouter()

predictor = FaultPredictor()
reasoner = HazardReasoner()
agv_guard = AgvGuard()
safety = SafetyController()

_predictions: dict[tuple[str, str], dict] = {}
_prediction_times: dict[tuple[str, str], float] = {}
PREDICTION_TTL_S = float(os.getenv("PREDICTION_TTL_S", "60"))
_hazards: list[dict] = []
_agv_state: dict[str, dict] = {}
_control_queue: list[dict] = []

MAX_HAZARDS = 100
MAX_CONTROL_QUEUE = 50


def _prediction_dict(p) -> dict:
    return p.to_dict()


def process_reading(
    device_id: str,
    subsystem: str,
    protocol: str,
    measurements: list[dict],
    timestamp: Optional[float] = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "predictions": [],
        "hazards": [],
        "agv": None,
        "control_commands": [],
        "safety_actions": [],
    }

    for measurement in measurements:
        key = (device_id, str(measurement.get("type", "")).lower())
        _predictions.pop(key, None)
        _prediction_times.pop(key, None)
    for p in predictor.push_measurements(device_id, measurements, timestamp):
        d = _prediction_dict(p)
        _predictions[(p.device_id, p.property_name)] = d
        _prediction_times[(p.device_id, p.property_name)] = time.time() if timestamp is None else timestamp
        result["predictions"].append(d)

    for h in reasoner.observe(device_id, subsystem, protocol, measurements, timestamp):
        d = h.to_dict()
        _hazards.insert(0, d)
        del _hazards[MAX_HAZARDS:]
        result["hazards"].append(d)

    engaged = safety.on_hazards(result["hazards"], timestamp)
    for action in engaged:
        source = next(
            (h for h in result["hazards"] if h.get("rule_name") == action.trigger),
            {"rule_name": action.trigger, "evidence": []},
        )
        decision = ledger.record(
            policy_name=action.policy_name,
            label_zh=action.label_zh,
            hazard=source,
            target_device=action.device_id,
            action=action.action,
            params=action.params,
            severity=action.severity,
            ontology_version=meta_registry.version,
        )
        payload = action.to_dict()
        payload["decision_id"] = decision.decision_id
        result["safety_actions"].append(payload)

    for action in safety.tick(timestamp):
        result["safety_actions"].append(action.to_dict())

    decision = agv_guard.push_measurements(device_id, measurements, timestamp)
    if decision is not None:
        d = decision.to_dict()
        _agv_state[device_id] = d
        result["agv"] = d
        if decision.action is not None:
            command = {
                "device_id": device_id,
                "action": decision.action,
                "subsystem": "agv",
                "params": {
                    "reason": decision.reason,
                    "distance_cm": round(decision.distance_cm, 1),
                },
            }
            _control_queue.insert(0, command)
            del _control_queue[MAX_CONTROL_QUEUE:]
            result["control_commands"].append(command)

    return result


@router.get("/api/v1/predictions")
async def list_predictions(device_id: Optional[str] = None) -> dict[str, Any]:
    cutoff = time.time() - PREDICTION_TTL_S
    items = [value for key, value in _predictions.items() if _prediction_times.get(key, 0) >= cutoff]
    if device_id:
        items = [p for p in items if p["device_id"] == device_id]
    items.sort(key=lambda p: p["seconds_to_threshold"] or 0.0)
    return {"items": items, "total": len(items)}


@router.get("/api/v1/hazards")
async def list_hazards(
    severity: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    items = _hazards
    if severity:
        items = [h for h in items if h["severity"] == severity]
    return {"items": items[:limit], "total": len(items)}


@router.get("/api/v1/agv")
async def agv_status(device_id: Optional[str] = None) -> dict[str, Any]:
    if device_id:
        state = _agv_state.get(device_id)
        return {"items": [state] if state else [], "total": 1 if state else 0}
    items = list(_agv_state.values())
    return {"items": items, "total": len(items)}


@router.get("/api/v1/agv/commands")
async def agv_commands(limit: int = Query(20, ge=1, le=50)) -> dict[str, Any]:
    return {"items": _control_queue[:limit], "total": len(_control_queue)}


@router.get("/api/v1/safety")
async def safety_status() -> dict[str, Any]:
    return {
        "enabled": safety.enabled,
        "engaged": safety.engaged_policies(),
        "policies": [
            {
                "name": p.name,
                "label_zh": p.label_zh,
                "triggers": list(p.hazard_rules),
                "target": p.target_device,
                "engage": p.engage_action,
                "engaged": safety.is_engaged(p.name),
            }
            for p in safety.policies
        ],
        "history": safety.history(limit=20),
    }


@router.post("/api/v1/safety/override/{policy_name}")
async def safety_override(policy_name: str, active: bool = True) -> dict[str, Any]:
    safety.set_manual_override(policy_name, active)
    return {"policy": policy_name, "manual_override": active}


@router.post("/api/v1/analytics/reset")
async def reset_analytics() -> dict[str, str]:
    predictor.reset()
    reasoner.reset()
    agv_guard.reset()
    safety.reset()
    ledger.reset()
    _predictions.clear()
    _prediction_times.clear()
    from backend.api.analytics_api import detector, alert_history
    detector._windows.clear()
    alert_history.clear()
    from analytics import trend_forecast
    trend_forecast.reset()
    _hazards.clear()
    _agv_state.clear()
    _control_queue.clear()
    return {"status": "reset"}
