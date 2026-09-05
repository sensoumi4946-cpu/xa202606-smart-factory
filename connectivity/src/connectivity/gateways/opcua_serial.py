"""Expose HC-SR04 serial readings as the bound OPC UA distance node."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os

logger = logging.getLogger(__name__)


def parse_distance(raw: bytes) -> float:
    payload = json.loads(raw.decode("utf-8"))
    value = float(payload["distance"])
    if not math.isfinite(value) or value < 0:
        raise ValueError("distance must be a finite non-negative value")
    return value


async def run(
    device: str,
    baud: int,
    endpoint: str,
    certificate: str,
    private_key: str,
    allow_insecure: bool,
) -> None:
    import serial
    from asyncua import Server, ua

    server = Server()
    await server.init()
    server.set_endpoint(endpoint)
    if certificate and private_key:
        await server.load_certificate(certificate)
        await server.load_private_key(private_key)
        server.set_security_policy([ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt])
    elif not allow_insecure:
        raise RuntimeError(
            "OPC UA certificate/private key required; use --allow-insecure only in an isolated lab"
        )
    namespace = await server.register_namespace("urn:xa202606:agv")
    if namespace != 2:
        raise RuntimeError(f"expected namespace 2 for bindings.ttl, got {namespace}")
    agv = await server.nodes.objects.add_object(namespace, "AGV")
    distance = await agv.add_variable(ua.NodeId("distance", namespace), "distance", 0.0)

    serial_port = serial.Serial(device, baudrate=baud, timeout=1)
    try:
        async with server:
            while True:
                raw = await asyncio.to_thread(serial_port.readline)
                if not raw:
                    continue
                try:
                    value = parse_distance(raw)
                except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    logger.warning("invalid serial reading: %s", exc)
                    continue
                await distance.write_value(value)
    finally:
        serial_port.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default=os.getenv("AGV_SERIAL_DEVICE", "/dev/ttyUSB0"))
    parser.add_argument("--baud", type=int, default=int(os.getenv("AGV_SERIAL_BAUD", "115200")))
    parser.add_argument("--endpoint", default=os.getenv("AGV_OPCUA_ENDPOINT", "opc.tcp://0.0.0.0:4840/"))
    parser.add_argument("--certificate", default=os.getenv("AGV_OPCUA_CERTIFICATE", ""))
    parser.add_argument("--private-key", default=os.getenv("AGV_OPCUA_PRIVATE_KEY", ""))
    parser.add_argument(
        "--allow-insecure",
        action="store_true",
        default=os.getenv("AGV_OPCUA_ALLOW_INSECURE", "false").lower() == "true",
    )
    args = parser.parse_args()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    asyncio.run(
        run(
            args.device,
            args.baud,
            args.endpoint,
            args.certificate,
            args.private_key,
            args.allow_insecure,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
