# extends the alert pipeline

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, SOSA

logger = logging.getLogger(__name__)

SF = Namespace("http://example.org/smart-factory#")


@dataclass(frozen=True)
class ContextRule:
    
    name: str
    observable_property: str
    threshold: float
    op: str = ">"
    level: str = "warning"
    required_subsystem: Optional[str] = None
    required_protocol: Optional[str] = None
    time_window: Optional[tuple[str, str]] = None
    co_required_property: Optional[str] = None
    co_threshold: float = 0.0


# Default ruleset

DEFAULT_CONTEXT_RULES: list[ContextRule] = [
    # Base rules (replicate existing threshold rules)
    ContextRule("high_temp",   "measuresTemperature",  38.0, ">", "warning"),
    ContextRule("smoke_warn",  "measuresSmoke",         8.0, ">", "warning"),
    ContextRule("co_critical", "measuresCO",           35.0, ">", "critical"),
    ContextRule("gas_leak",    "measuresCombustibleGas", 3.0, ">", "critical"),
    ContextRule("agv_close",   "measuresDistance",     30.0, "<", "warning"),

    ContextRule(
        name="night_co_tight",
        observable_property="measuresCO",
        threshold=20.0,
        op=">",
        level="critical",
        required_subsystem="GasMonitoringSubsystem",
        time_window=("22:00", "06:00"),   # tighter at night
    ),
    ContextRule(
        name="modbus_high_temp_crosscheck",
        observable_property="measuresTemperature",
        threshold=32.0,
        op=">",
        level="warning",
        required_protocol="modbus",
        co_required_property="measuresSmoke",
        co_threshold=5.0,
    ),
    ContextRule(
        name="gas_subsystem_co_tight",
        observable_property="measuresCO",
        threshold=25.0,
        op=">",
        level="critical",
        required_subsystem="GasMonitoringSubsystem",
        required_protocol="modbus",
    ),
]


# Context resolver

def _in_time_window(window: tuple[str, str]) -> bool:
    now = datetime.now(timezone.utc)
    hm_now = now.hour * 60 + now.minute

    def hm(s: str) -> int:
        h, m = s.split(":")
        return int(h) * 60 + int(m)

    start = hm(window[0])
    end   = hm(window[1])
    if start <= end:
        return start <= hm_now < end
    return hm_now >= start or hm_now < end


def _sensor_subsystem(graph: Graph, device_id: str) -> Optional[str]:
    sensor_uri = URIRef(f"{SF}{device_id}")
    for obj in graph.objects(sensor_uri, SF.belongsToSubsystem):
        s = str(obj)
        return s.rsplit("#", 1)[-1] if "#" in s else s.rsplit("/", 1)[-1]
    return None


def _sensor_protocol(graph: Graph, device_id: str) -> Optional[str]:
    sensor_uri = URIRef(f"{SF}{device_id}")
    for obj in graph.objects(sensor_uri, SF.transportedVia):
        return str(obj)
    return None


def _any_recent_observation(
    graph: Graph,
    observable_property: str,
    threshold: float,
    exclude_device: str,
) -> bool:
    prop_uri = URIRef(f"{SF}{observable_property}")
    exclude_uri = URIRef(f"{SF}{exclude_device}")

    for obs in graph.subjects(RDF.type, SOSA.Observation):
        props = list(graph.objects(obs, SOSA.observedProperty))
        if prop_uri not in props:
            continue
        sensors = list(graph.objects(obs, SOSA.madeBySensor))
        if exclude_uri in sensors:
            continue
        for result in graph.objects(obs, SOSA.hasSimpleResult):
            try:
                if float(result) > threshold:
                    return True
            except (TypeError, ValueError):
                pass
    return False


# Evaluation engine

@dataclass
class SemanticAlert:
    rule_name: str
    level: str
    device_id: str
    measurement_type: str
    value: float
    threshold: float
    context: dict = field(default_factory=dict)
    message: str = ""


def evaluate_with_context(
    device_id: str,
    observable_property: str,
    value: float,
    graph: Graph,
    rules: Optional[list[ContextRule]] = None,
) -> list[SemanticAlert]:
    if rules is None:
        rules = DEFAULT_CONTEXT_RULES

    alerts: list[SemanticAlert] = []

    # Resolve KG context once per call
    subsystem = _sensor_subsystem(graph, device_id)
    protocol  = _sensor_protocol(graph, device_id)

    for rule in rules:
        if rule.observable_property != observable_property:
            continue
        if rule.op == ">" and not (value > rule.threshold):
            continue
        if rule.op == "<" and not (value < rule.threshold):
            continue
        if rule.required_subsystem and subsystem != rule.required_subsystem:
            continue
        if rule.required_protocol and protocol != rule.required_protocol:
            continue
        if rule.time_window and not _in_time_window(rule.time_window):
            continue
        if rule.co_required_property:
            if not _any_recent_observation(
                graph,
                rule.co_required_property,
                rule.co_threshold,
                exclude_device=device_id,
            ):
                continue

        ctx = {
            "subsystem": subsystem,
            "protocol": protocol,
            "kg_enriched": True,
        }
        alerts.append(SemanticAlert(
            rule_name=rule.name,
            level=rule.level,
            device_id=device_id,
            measurement_type=observable_property,
            value=value,
            threshold=rule.threshold,
            context=ctx,
            message=(
                f"[{rule.level.upper()}] {rule.name}: "
                f"{observable_property}={value} (threshold={rule.threshold}) "
                f"on {device_id} [{subsystem or '?'}/{protocol or '?'}]"
            ),
        ))

    return alerts
