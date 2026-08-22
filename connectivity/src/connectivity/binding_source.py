from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from semantic_layer.protocol_binding import (
    BindingRegistry,
    ProtocolBinding,
    canonical_subsystem,
)

logger = logging.getLogger(__name__)

BINDINGS_FILENAME = "bindings.ttl"

BINDINGS_ENV_VAR = "BINDINGS_TTL"


def find_bindings_file(start: str | Path | None = None) -> Optional[Path]:
    override = os.getenv(BINDINGS_ENV_VAR)
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file():
            return candidate.resolve()
        logger.warning("%s=%s does not exist", BINDINGS_ENV_VAR, override)
        return None

    origin = Path(start or __file__).resolve()
    for parent in (origin, *origin.parents):
        candidate = parent / BINDINGS_FILENAME
        if candidate.is_file():
            return candidate
    return None


def load_registry(path: str | Path | None = None) -> BindingRegistry:
    registry = BindingRegistry()
    target = Path(path) if path is not None else find_bindings_file()

    if target is None or not target.is_file():
        logger.warning("no %s found; binding source is empty", BINDINGS_FILENAME)
        return registry

    result = registry.load_turtle(target.read_text(encoding="utf-8"))
    if not result.accepted:
        logger.error("bindings file %s rejected: %s", target, result.violations)
        return BindingRegistry()

    logger.info(
        "loaded %d protocol bindings from %s covering devices %s",
        len(registry),
        target,
        registry.devices(),
    )
    return registry


class BindingSource:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else find_bindings_file()
        self.registry = load_registry(self.path)

    @property
    def empty(self) -> bool:
        return len(self.registry) == 0

    def reload(self) -> "BindingSource":
        self.path = self.path or find_bindings_file()
        self.registry = load_registry(self.path)
        return self

    def for_protocol(self, protocol: str) -> list[ProtocolBinding]:
        return self.registry.for_protocol(protocol)

    def for_device(self, device_id: str) -> list[ProtocolBinding]:
        return self.registry.for_device(device_id)

    def resolve_device_id(self, candidate: Any) -> Optional[str]:
        return self.registry.resolve_device_id(candidate)

    def aliases(self) -> dict[str, str]:
        return self.registry.aliases()

    def devices(self) -> list[str]:
        return self.registry.devices()

    def subsystem_for(self, device_id: str) -> str:
        for binding in self.for_device(device_id):
            if binding.subsystem:
                return binding.canonical_subsystem
        return ""

    def slave_ids(self) -> list[int]:
        return sorted(
            {
                b.slave_id
                for b in self.for_protocol("modbus")
                if b.register_address is not None
            }
        )

    def modbus_entries(self, slave_id: Optional[int] = None) -> list[ProtocolBinding]:
        entries = [
            b
            for b in self.for_protocol("modbus")
            if b.register_address is not None
            and (slave_id is None or b.slave_id == slave_id)
        ]
        entries.sort(key=lambda b: (b.slave_id, b.wire_address or 0))
        return entries

    def read_plan(self) -> list[dict[str, Any]]:
        groups: dict[tuple[int, int, int], list[ProtocolBinding]] = {}
        for binding in self.modbus_entries():
            key = (binding.slave_id, binding.function_code, binding.poll_interval_ms)
            groups.setdefault(key, []).append(binding)

        plan = []
        for key in sorted(groups):
            slave_id, function_code, poll_interval_ms = key
            entries = groups[key]
            start = min(b.wire_address or 0 for b in entries)
            end = max((b.wire_address or 0) + b.register_count for b in entries)
            plan.append(
                {
                    "slave_id": slave_id,
                    "function_code": function_code,
                    "poll_interval_ms": poll_interval_ms,
                    "start_address": start,
                    "count": end - start,
                    "entries": entries,
                }
            )
        return plan

    def opcua_nodes(self) -> list[dict[str, Any]]:
        return [
            {
                "device_id": b.device_id,
                "property_name": b.property_name,
                "canonical_subsystem": b.canonical_subsystem,
                "node_id": f"ns={b.namespace_index};s={b.node_id}",
                "scale_factor": b.scale_factor,
                "offset": b.offset,
                "poll_interval_ms": b.poll_interval_ms,
            }
            for b in self.for_protocol("opcua")
            if b.node_id
        ]

    def mqtt_subscriptions(self) -> list[tuple[str, int]]:
        subs = set()
        for b in self.for_protocol("mqtt"):
            topic = (
                b.topic
                or f"factory/{b.canonical_subsystem}/sensors/{b.device_id}/{b.property_name}"
            )
            subs.add((topic, b.qos))
        return sorted(subs)

    def rest_routes(self) -> list[tuple[str, str]]:
        return sorted(
            {
                (b.path or "/adapter/rest/ingest", b.method)
                for b in self.for_protocol("rest")
            }
        )

    def summary(self) -> dict[str, Any]:
        return {
            "path": str(self.path) if self.path else None,
            "total_bindings": len(self.registry),
            "devices": self.devices(),
            "aliases": self.aliases(),
            "modbus_registers": len(self.modbus_entries()),
            "opcua_nodes": len(self.opcua_nodes()),
            "mqtt_topics": len(self.mqtt_subscriptions()),
            "rest_routes": len(self.rest_routes()),
        }


binding_source = BindingSource()


def subsystem_of(binding: ProtocolBinding) -> str:
    return canonical_subsystem(binding.subsystem)
