from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any, Optional

from semantic_layer.protocol_binding import BindingRegistry, generate_all

logger = logging.getLogger("sf-bindingd")

DEFAULT_SOCKET = os.getenv("SF_BINDING_SOCKET", "/run/xa202606/bindings.sock")
MAX_REQUEST_BYTES = 64 * 1024
PROTOCOL_VERSION = 1


def find_bindings_file(explicit: Optional[str] = None) -> Optional[Path]:
    name = explicit or os.getenv("BINDINGS_TTL", "bindings.ttl")
    direct = Path(name)
    if direct.is_absolute() and direct.exists():
        return direct
    roots = [Path.cwd(), *Path(__file__).resolve().parents[:6]]
    for root in roots:
        candidate = (root / name).resolve()
        if candidate.exists():
            return candidate
    return None


class BindingService:
    def __init__(self, bindings_path: Path) -> None:
        self.bindings_path = bindings_path
        self.registry = BindingRegistry()
        self.loaded_at: Optional[str] = None
        self.reload()

    def reload(self) -> dict[str, Any]:
        import datetime

        fresh = BindingRegistry()
        result = fresh.load_turtle(self.bindings_path.read_text(encoding="utf-8"))
        if not result.accepted:
            logger.error("reload rejected: %s", result.violations)
            return {"ok": False, "violations": result.violations}
        self.registry = fresh
        self.loaded_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        logger.info(
            "loaded %d bindings, %d devices from %s",
            len(fresh),
            len(fresh.devices()),
            self.bindings_path,
        )
        return {
            "ok": True,
            "bindings": len(fresh),
            "devices": fresh.devices(),
            "loaded_at": self.loaded_at,
        }

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        op = request.get("op", "")

        if op == "ping":
            return {"ok": True, "version": PROTOCOL_VERSION}

        if op == "status":
            return {
                "ok": True,
                "version": PROTOCOL_VERSION,
                "source": str(self.bindings_path),
                "loaded_at": self.loaded_at,
                "bindings": len(self.registry),
                "devices": self.registry.devices(),
                "protocols": sorted({b.protocol for b in self.registry.all()}),
                "aliases": self.registry.aliases(),
            }

        if op == "devices":
            return {"ok": True, "devices": self.registry.devices()}

        if op == "resolve":
            device_id = request.get("device_id", "")
            if not device_id:
                return {"ok": False, "error": "device_id required"}
            canonical = self.registry.resolve_device_id(device_id)
            return {
                "ok": True,
                "reported": device_id,
                "device_id": canonical,
                "aliased": canonical != device_id,
            }

        if op == "describe":
            device_id = request.get("device_id", "")
            if not device_id:
                return {"ok": False, "error": "device_id required"}
            canonical = self.registry.resolve_device_id(device_id)
            bindings = self.registry.for_device(canonical)
            if not bindings:
                return {"ok": False, "error": f"unknown device {device_id}"}
            return {
                "ok": True,
                "device_id": canonical,
                "bindings": [b.to_dict() for b in bindings],
            }

        if op == "read_plan":
            device_id = request.get("device_id", "")
            protocol = request.get("protocol", "modbus")
            selected = [
                b
                for b in self.registry.for_protocol(protocol)
                if not device_id or b.matches_device(device_id)
            ]
            if not selected:
                return {"ok": False, "error": "no bindings match"}
            return {
                "ok": True,
                "protocol": protocol,
                "entries": [
                    {
                        "device_id": b.device_id,
                        "property_name": b.property_name,
                        "wire_address": b.wire_address,
                        "declared_address": b.register_address,
                        "function_code": b.function_code,
                        "register_type": b.register_type,
                        "scale_factor": b.scale_factor,
                        "poll_interval_ms": b.poll_interval_ms,
                        "node_id": b.node_id,
                        "topic": b.topic,
                        "path": b.path,
                    }
                    for b in selected
                ],
            }

        if op == "adapter":
            protocol = request.get("protocol", "")
            adapters = generate_all(self.registry)
            if protocol not in adapters:
                return {
                    "ok": False,
                    "error": f"no generator for {protocol}",
                    "available": sorted(adapters),
                }
            return {"ok": True, "protocol": protocol, "source": adapters[protocol]}

        if op == "reload":
            return self.reload()

        return {"ok": False, "error": f"unknown op {op!r}"}


async def _serve_client(
    service: BindingService,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    try:
        raw = await asyncio.wait_for(reader.readline(), timeout=5.0)
        if not raw:
            return
        if len(raw) > MAX_REQUEST_BYTES:
            response = {"ok": False, "error": "request too large"}
        else:
            try:
                request = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as exc:
                response = {"ok": False, "error": f"bad json: {exc}"}
            else:
                response = service.handle(request)
        writer.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
        await writer.drain()
    except asyncio.TimeoutError:
        pass
    except Exception as exc:
        logger.warning("client error: %s", exc)
    finally:
        writer.close()


async def run(socket_path: str, bindings_path: Path) -> int:
    service = BindingService(bindings_path)

    target = Path(socket_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()

        start_unix_server = getattr(asyncio, "start_unix_server", None)
    if start_unix_server is None:
        logger.error("Unix domain sockets are not available on this platform")
        return 1

    server = await start_unix_server(
        lambda r, w: _serve_client(service, r, w), path=socket_path
    )
    os.chmod(socket_path, 0o660)
    logger.info("listening on %s", socket_path)

    loop = asyncio.get_running_loop()
    stop = loop.create_future()

    def _shutdown(*_: Any) -> None:
        if not stop.done():
            stop.set_result(None)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            signal.signal(sig, _shutdown)

        sighup = getattr(signal, "SIGHUP", None)
    if sighup is not None:
        try:
            loop.add_signal_handler(sighup, lambda: service.reload())
        except (NotImplementedError, AttributeError):
            pass

    async with server:
        await stop

    logger.info("shutting down")
    if target.exists():
        target.unlink()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="XA-202606 binding service")
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    parser.add_argument("--bindings", default=None)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s %(name)s %(message)s",
    )

    bindings = find_bindings_file(args.bindings)
    if bindings is None:
        logger.error("bindings.ttl not found; cannot start")
        return 1

    return asyncio.run(run(args.socket, bindings))


if __name__ == "__main__":
    sys.exit(main())