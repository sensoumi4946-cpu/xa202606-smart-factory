from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import connectivity.models as connectivity_models
from connectivity.binding_source import BindingSource, binding_source

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    device: str
    ok: bool
    message: str
    protocol: str = ""
    device_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "device": self.device,
            "ok": self.ok,
            "message": self.message,
            "protocol": self.protocol,
            "device_ids": list(self.device_ids),
        }


def _tcp_reachable(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


async def _tcp_reachable_async(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


def _split_endpoint(url: str, default_port: int) -> tuple[str, int]:
    parsed = urlparse(url if "://" in url else f"//{url}")
    host = parsed.hostname or "localhost"
    port = parsed.port or default_port
    return host, port


def _result(label: str, protocol: str, ok: bool, device_ids) -> ValidationResult:
    return ValidationResult(
        device=label,
        ok=ok,
        message="reachable" if ok else "TCP connection refused or timed out",
        protocol=protocol,
        device_ids=tuple(sorted(set(device_ids))),
    )


async def validate_endpoints(
    source: Optional[BindingSource] = None,
) -> list[ValidationResult]:
    source = source or binding_source
    results: list[ValidationResult] = []

    modbus = source.modbus_entries()
    if modbus:
        host, port = connectivity_models.MODBUS_HOST, connectivity_models.MODBUS_PORT
        ok = await _tcp_reachable_async(host, port)
        results.append(
            _result(
                f"Modbus {host}:{port}",
                "modbus",
                ok,
                (b.device_id for b in modbus),
            )
        )

    opcua = source.opcua_nodes()
    if opcua:
        host, port = _split_endpoint(connectivity_models.OPCUA_ENDPOINT, 4840)
        ok = await _tcp_reachable_async(host, port)
        results.append(
            _result(
                f"OPC-UA {connectivity_models.OPCUA_ENDPOINT}",
                "opcua",
                ok,
                (n["device_id"] for n in opcua),
            )
        )

    mqtt = source.for_protocol("mqtt")
    if mqtt:
        host = connectivity_models.MQTT_BROKER_HOST
        port = connectivity_models.MQTT_BROKER_PORT
        ok = await _tcp_reachable_async(host, port)
        results.append(
            _result(
                f"MQTT {host}:{port}",
                "mqtt",
                ok,
                (b.device_id for b in mqtt),
            )
        )

    rest = source.for_protocol("rest")
    if rest:
        host, port = _split_endpoint(connectivity_models.BACKEND_URL, 8000)
        ok = await _tcp_reachable_async(host, port)
        results.append(
            _result(
                f"Backend {connectivity_models.BACKEND_URL}",
                "rest",
                ok,
                (b.device_id for b in rest),
            )
        )

    return results


def undeclared_bindings(source: Optional[BindingSource] = None) -> list[str]:
    source = source or binding_source
    problems = []
    for binding in source.for_protocol("modbus"):
        if binding.register_address is None:
            problems.append(
                f"{binding.binding_id}: modbus binding without sf:registerAddress"
            )
    for binding in source.for_protocol("opcua"):
        if not binding.node_id:
            problems.append(f"{binding.binding_id}: opcua binding without sf:nodeId")
    for binding in source.registry.all():
        if not binding.canonical_subsystem:
            problems.append(
                f"{binding.binding_id}: binding without sf:belongsToSubsystem"
            )
    return problems


async def _main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--bindings", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    source = BindingSource(args.bindings) if args.bindings else binding_source

    print(f"\nValidating bindings: {source.path}\n{'=' * 40}")
    if source.empty:
        print("  no protocol bindings declared — nothing to validate")
        raise SystemExit(1)

    problems = undeclared_bindings(source)
    for problem in problems:
        print(f"  !  {problem}")

    results = await validate_endpoints(source)
    all_ok = not problems
    for r in results:
        status = "OK " if r.ok else "FAIL"
        devices = ", ".join(r.device_ids)
        print(f"  {status}  {r.device}: {r.message} [{devices}]")
        if not r.ok:
            all_ok = False
    print()

    if all_ok:
        print("All declared endpoints reachable. Safe to start adapters.")
    else:
        print("Fix the reported bindings or connectivity before hardware tests.")
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(_main())
