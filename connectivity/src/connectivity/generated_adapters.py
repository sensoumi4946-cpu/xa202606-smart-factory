from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from semantic_layer.protocol_binding import (
    BindingRegistry,
    ProtocolBinding,
    decode_registers,
)

logger = logging.getLogger(__name__)

DEFAULT_BINDINGS = os.getenv("BINDINGS_TTL", "bindings.ttl")

UNIT_BY_PROPERTY = {
    "temperature": "celsius",
    "humidity": "percent",
    "co": "ppm",
    "smoke": "ppm",
    "combustible_gas": "ppm",
    "distance": "cm",
    "count": "count",
    "occupancy": "boolean",
    "light_state": "boolean",
    "vibration": "mm_per_sec",
    "pressure": "kpa",
}

SUBSYSTEM_ALIAS = {
    "temp_humidity_subsystem": "temp_humidity",
    "gas_subsystem": "gas",
    "agv_subsystem": "agv",
    "counting_subsystem": "counting",
    "lighting_subsystem": "lighting",
    "vibration_subsystem": "vibration",
}


def _subsystem(binding: ProtocolBinding) -> str:
    return SUBSYSTEM_ALIAS.get(binding.subsystem, binding.subsystem)


def _unit(property_name: str) -> str:
    return UNIT_BY_PROPERTY.get(property_name, "")


class GeneratedAdapterSet:
    def __init__(self, registry: BindingRegistry) -> None:
        self.registry = registry

    @property
    def empty(self) -> bool:
        return len(self.registry) == 0

    def modbus_plan(self) -> list[dict[str, Any]]:
        plan = []
        for binding in self.registry.for_protocol("modbus"):
            if binding.register_address is None:
                logger.warning(
                    "modbus binding %s has no register address, skipped",
                    binding.binding_id,
                )
                continue
            plan.append(
                {
                    "device_id": binding.device_id,
                    "property_name": binding.property_name,
                    "subsystem": _subsystem(binding),
                    "unit": _unit(binding.property_name),
                    "address": binding.register_address,
                    "count": binding.register_count,
                    "register_type": binding.register_type,
                    "word_order": binding.word_order,
                    "byte_order": binding.byte_order,
                    "scale_factor": binding.scale_factor,
                    "offset": binding.offset,
                    "slave_id": binding.slave_id,
                    "poll_interval_ms": binding.poll_interval_ms,
                }
            )
        plan.sort(key=lambda e: (e["slave_id"], e["address"]))
        return plan

    def modbus_read_span(self, slave_id: int) -> Optional[tuple[int, int]]:
        entries = [e for e in self.modbus_plan() if e["slave_id"] == slave_id]
        if not entries:
            return None
        start = min(e["address"] for e in entries)
        end = max(e["address"] + e["count"] for e in entries)
        return start, end - start

    def decode_modbus_block(
        self, slave_id: int, words: list[int], start_address: int
    ) -> list[dict[str, Any]]:
        readings = []
        for entry in self.modbus_plan():
            if entry["slave_id"] != slave_id:
                continue
            offset = entry["address"] - start_address
            if offset < 0 or offset + entry["count"] > len(words):
                continue
            slice_ = words[offset : offset + entry["count"]]
            try:
                value = decode_registers(
                    slice_,
                    register_type=entry["register_type"],
                    word_order=entry["word_order"],
                    byte_order=entry["byte_order"],
                    scale_factor=entry["scale_factor"],
                    offset=entry["offset"],
                )
            except ValueError as exc:
                logger.warning("decode failed for %s: %s", entry["property_name"], exc)
                continue
            readings.append(
                {
                    "device_id": entry["device_id"],
                    "subsystem": entry["subsystem"],
                    "property_name": entry["property_name"],
                    "value": round(value, 4),
                    "unit": entry["unit"],
                }
            )
        return readings

    def messages_from_modbus_block(
        self, slave_id: int, words: list[int], start_address: int
    ) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], list[dict]] = {}
        for reading in self.decode_modbus_block(slave_id, words, start_address):
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
                "device_id": b.device_id,
                "property_name": b.property_name,
                "subsystem": _subsystem(b),
                "unit": _unit(b.property_name),
                "node_id": f"ns={b.namespace_index};s={b.node_id}",
                "scale_factor": b.scale_factor,
                "offset": b.offset,
                "poll_interval_ms": b.poll_interval_ms,
            }
            for b in self.registry.for_protocol("opcua")
            if b.node_id
        ]

    def message_from_opcua(
        self, node_id: str, raw_value: float
    ) -> Optional[dict[str, Any]]:
        for node in self.opcua_nodes():
            if node["node_id"] != node_id:
                continue
            value = float(raw_value) * node["scale_factor"] + node["offset"]
            return {
                "schema_version": "v1",
                "device_id": node["device_id"],
                "subsystem": node["subsystem"],
                "protocol": "opcua",
                "measurements": [
                    {
                        "type": node["property_name"],
                        "value": round(value, 4),
                        "unit": node["unit"],
                    }
                ],
            }
        return None

    def mqtt_subscriptions(self) -> list[tuple[str, int]]:
        subs = []
        for b in self.registry.for_protocol("mqtt"):
            topic = (
                b.topic
                or f"factory/{_subsystem(b)}/sensors/{b.device_id}/{b.property_name}"
            )
            subs.append((topic, b.qos))
        return sorted(set(subs))

    def rest_routes(self) -> list[dict[str, Any]]:
        return [
            {
                "device_id": b.device_id,
                "property_name": b.property_name,
                "subsystem": _subsystem(b),
                "path": b.path or "/adapter/rest/ingest",
                "method": b.method,
            }
            for b in self.registry.for_protocol("rest")
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
    target = Path(path or DEFAULT_BINDINGS)
    registry = BindingRegistry()

    if not target.exists():
        logger.warning(
            "bindings file %s not found — generated adapters disabled, "
            "falling back to hand-written mapping",
            target,
        )
        return GeneratedAdapterSet(registry)

    result = registry.load_turtle(target.read_text(encoding="utf-8"))
    if not result.accepted:
        logger.error("bindings file %s rejected: %s", target, result.violations)
        return GeneratedAdapterSet(BindingRegistry())

    logger.info(
        "loaded %d protocol bindings from %s covering devices %s",
        len(registry),
        target,
        registry.devices(),
    )
    return GeneratedAdapterSet(registry)


adapter_set = load_adapter_set()
