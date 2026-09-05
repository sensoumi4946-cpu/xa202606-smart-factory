"""Runtime views generated from the protocol-binding ontology.

This module contains protocol plumbing only.  Device addresses, units,
subsystems, scaling, topics, and node identifiers come from ``bindings.ttl``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from semantic_layer.protocol_binding import (
    BindingRegistry,
    ProtocolBinding,
    decode_registers,
)

logger = logging.getLogger(__name__)


def _default_bindings_path() -> Path:
    configured = os.getenv("BINDINGS_TTL")
    if configured:
        return Path(configured)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "bindings.ttl"
        if candidate.exists():
            return candidate
    return Path("bindings.ttl")


class GeneratedAdapterSet:
    """Typed protocol plans backed by one validated binding registry."""

    def __init__(self, registry: BindingRegistry) -> None:
        self.registry = registry

    @property
    def empty(self) -> bool:
        return len(self.registry) == 0

    def modbus_plan(self) -> list[dict[str, Any]]:
        plan: list[dict[str, Any]] = []
        for binding in self.registry.for_protocol("modbus"):
            if binding.wire_address is None:
                logger.warning(
                    "modbus binding %s has no register address; skipped",
                    binding.binding_id,
                )
                continue
            plan.append(
                {
                    "device_id": binding.device_id,
                    "property_name": binding.property_name,
                    "subsystem": binding.canonical_subsystem,
                    "unit": binding.unit,
                    "address": binding.wire_address,
                    "declared_address": binding.register_address,
                    "count": binding.register_count,
                    "register_type": binding.register_type,
                    "word_order": binding.word_order,
                    "byte_order": binding.byte_order,
                    "scale_factor": binding.scale_factor,
                    "offset": binding.offset,
                    "slave_id": binding.slave_id,
                    "function_code": binding.function_code,
                    "poll_interval_ms": binding.poll_interval_ms,
                }
            )
        return sorted(
            plan,
            key=lambda item: (
                item["poll_interval_ms"],
                item["slave_id"],
                item["function_code"],
                item["address"],
            ),
        )

    def modbus_read_plans(self) -> list[dict[str, Any]]:
        groups: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
        for entry in self.modbus_plan():
            key = (
                entry["slave_id"],
                entry["function_code"],
                entry["poll_interval_ms"],
            )
            groups.setdefault(key, []).append(entry)

        plans: list[dict[str, Any]] = []
        for (slave_id, function_code, interval_ms), entries in groups.items():
            start = min(entry["address"] for entry in entries)
            end = max(entry["address"] + entry["count"] for entry in entries)
            plans.append(
                {
                    "slave_id": slave_id,
                    "function_code": function_code,
                    "poll_interval_ms": interval_ms,
                    "address": start,
                    "count": end - start,
                    "entries": entries,
                }
            )
        return sorted(
            plans,
            key=lambda item: (
                item["poll_interval_ms"],
                item["slave_id"],
                item["function_code"],
                item["address"],
            ),
        )

    def modbus_read_span(self, slave_id: int) -> tuple[int, int] | None:
        entries = [e for e in self.modbus_plan() if e["slave_id"] == slave_id]
        if not entries:
            return None
        start = min(e["address"] for e in entries)
        end = max(e["address"] + e["count"] for e in entries)
        return start, end - start

    def decode_modbus_block(
        self,
        slave_id: int,
        words: list[int],
        start_address: int,
        function_code: int | None = None,
    ) -> list[dict[str, Any]]:
        readings: list[dict[str, Any]] = []
        for entry in self.modbus_plan():
            if entry["slave_id"] != slave_id:
                continue
            if function_code is not None and entry["function_code"] != function_code:
                continue
            offset = entry["address"] - start_address
            if offset < 0 or offset + entry["count"] > len(words):
                continue
            try:
                value = decode_registers(
                    words[offset : offset + entry["count"]],
                    register_type=entry["register_type"],
                    word_order=entry["word_order"],
                    byte_order=entry["byte_order"],
                    scale_factor=entry["scale_factor"],
                    offset=entry["offset"],
                )
            except ValueError as exc:
                logger.warning(
                    "decode failed for binding %s: %s", entry["property_name"], exc
                )
                continue
            readings.append({**entry, "value": round(value, 6)})
        return readings

    def messages_from_modbus_block(
        self,
        slave_id: int,
        words: list[int],
        start_address: int,
        function_code: int | None = None,
    ) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for reading in self.decode_modbus_block(
            slave_id, words, start_address, function_code
        ):
            key = (reading["device_id"], reading["subsystem"])
            grouped.setdefault(key, []).append(
                {
                    "type": reading["property_name"],
                    "value": reading["value"],
                    "unit": reading["unit"],
                }
            )
        return [
            {
                "schema_version": "v1",
                "device_id": device_id,
                "subsystem": subsystem,
                "protocol": "modbus",
                "measurements": measurements,
            }
            for (device_id, subsystem), measurements in sorted(grouped.items())
        ]

    def opcua_nodes(self) -> list[dict[str, Any]]:
        return [
            {
                "device_id": binding.device_id,
                "property_name": binding.property_name,
                "subsystem": binding.canonical_subsystem,
                "unit": binding.unit,
                "node_id": f"ns={binding.namespace_index};s={binding.node_id}",
                "scale_factor": binding.scale_factor,
                "offset": binding.offset,
                "poll_interval_ms": binding.poll_interval_ms,
            }
            for binding in self.registry.for_protocol("opcua")
            if binding.node_id
        ]

    def message_from_opcua(
        self, node_id: str, raw_value: float
    ) -> dict[str, Any] | None:
        for entry in self.opcua_nodes():
            if entry["node_id"] != node_id:
                continue
            return {
                "schema_version": "v1",
                "device_id": entry["device_id"],
                "subsystem": entry["subsystem"],
                "protocol": "opcua",
                "measurements": [
                    {
                        "type": entry["property_name"],
                        "value": round(
                            float(raw_value) * entry["scale_factor"] + entry["offset"],
                            6,
                        ),
                        "unit": entry["unit"],
                    }
                ],
            }
        return None

    def mqtt_entries(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for binding in self.registry.for_protocol("mqtt"):
            topic = binding.topic or (
                f"factory/{binding.canonical_subsystem}/sensors/"
                f"{binding.device_id}/{binding.property_name}"
            )
            entries.append(
                {
                    "device_id": binding.device_id,
                    "property_name": binding.property_name,
                    "subsystem": binding.canonical_subsystem,
                    "unit": binding.unit,
                    "topic": topic,
                    "qos": binding.qos,
                    "scale_factor": binding.scale_factor,
                    "offset": binding.offset,
                }
            )
        return entries

    def mqtt_subscriptions(self) -> list[tuple[str, int]]:
        return sorted({(e["topic"], e["qos"]) for e in self.mqtt_entries()})

    def mqtt_entry(self, topic: str) -> dict[str, Any] | None:
        return next((e for e in self.mqtt_entries() if e["topic"] == topic), None)

    def rest_routes(self) -> list[dict[str, Any]]:
        return [
            {
                "device_id": binding.device_id,
                "property_name": binding.property_name,
                "subsystem": binding.canonical_subsystem,
                "unit": binding.unit,
                "path": binding.path or "/adapter/rest/ingest",
                "method": binding.method,
            }
            for binding in self.registry.for_protocol("rest")
        ]

    def summary(self) -> dict[str, Any]:
        return {
            "total_bindings": len(self.registry),
            "modbus_registers": len(self.modbus_plan()),
            "opcua_nodes": len(self.opcua_nodes()),
            "mqtt_topics": len(self.mqtt_subscriptions()),
            "rest_routes": len(self.rest_routes()),
            "devices": self.registry.devices(),
        }


def load_adapter_set(path: str | Path | None = None) -> GeneratedAdapterSet:
    target = Path(path) if path is not None else _default_bindings_path()
    registry = BindingRegistry()
    if not target.exists():
        logger.error("bindings file %s not found; protocol adapters disabled", target)
        return GeneratedAdapterSet(registry)

    result = registry.load_turtle(target.read_text(encoding="utf-8"))
    if not result.accepted:
        logger.error("bindings file %s rejected: %s", target, result.violations)
        return GeneratedAdapterSet(BindingRegistry())
    return GeneratedAdapterSet(registry)


adapter_set = load_adapter_set()
