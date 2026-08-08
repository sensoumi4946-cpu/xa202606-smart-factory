# Pre-connection hardware validation
from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    device: str
    ok: bool
    message: str


def _tcp_reachable(host: str, port: int, timeout: float = 3.0) -> bool:
    # works for Modbus (502) and MQTT (1883)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


async def _opcua_reachable(endpoint_url: str) -> bool:
    
    try:
        parts = endpoint_url.replace("opc.tcp://", "").split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 4840
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=3.0
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


async def validate_profile(profile_name: str = "mock") -> list[ValidationResult]:
    
    # Returns a list of ValidationResult — one per device

    from connectivity.hardware_profiles import get_profile
    profile = get_profile(profile_name)
    results: list[ValidationResult] = []

    # Modbus devices
    for dev in profile.modbus_devices:
        ok = _tcp_reachable(dev.host, dev.port)
        results.append(ValidationResult(
            device=f"Modbus {dev.host}:{dev.port}",
            ok=ok,
            message="reachable" if ok else f"TCP connection refused or timed out",
        ))

    for dev in profile.opcua_devices:
        ok = await _opcua_reachable(dev.endpoint_url)
        results.append(ValidationResult(
            device=f"OPC-UA {dev.endpoint_url}",
            ok=ok,
            message="reachable" if ok else "TCP connection refused or timed out",
        ))

    if profile.mqtt_config:
        ok = _tcp_reachable(profile.mqtt_config.broker_host, profile.mqtt_config.broker_port)
        results.append(ValidationResult(
            device=f"MQTT {profile.mqtt_config.broker_host}:{profile.mqtt_config.broker_port}",
            ok=ok,
            message="reachable" if ok else "TCP connection refused or timed out",
        ))

    return results


async def _main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="mock")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(f"\nValidating hardware profile: {args.profile}\n{'='*40}")
    results = await validate_profile(args.profile)
    all_ok = True
    for r in results:
        status = "✓" if r.ok else "✗"
        print(f"  {status}  {r.device}: {r.message}")
        if not r.ok:
            all_ok = False
    print()
    if all_ok:
        print("All devices reachable. Safe to start adapters.")
    else:
        print("Some devices unreachable. Fix connectivity before running hardware tests.")
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(_main())