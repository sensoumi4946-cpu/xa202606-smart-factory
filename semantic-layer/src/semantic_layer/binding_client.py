from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from typing import Any

DEFAULT_SOCKET = os.getenv("SF_BINDING_SOCKET", "/run/xa202606/bindings.sock")


class BindingClientError(RuntimeError):
    pass


def query(request: dict[str, Any], socket_path: str = DEFAULT_SOCKET) -> dict[str, Any]:
    af_unix = getattr(socket, "AF_UNIX", None)
    if af_unix is None:
        raise BindingClientError(
            "Unix domain sockets are not available on this platform; "
            "run the CLI on the openEuler host"
        )
    try:
        sock = socket.socket(af_unix, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect(socket_path)
    except OSError as exc:
        raise BindingClientError(f"cannot reach {socket_path}: {exc}") from exc

    with sock:
        sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            if chunks[-1].endswith(b"\n"):
                break

    payload = b"".join(chunks).decode("utf-8").strip()
    if not payload:
        raise BindingClientError("empty response")
    return json.loads(payload)


def resolve(device_id: str, socket_path: str = DEFAULT_SOCKET) -> str:
    reply = query({"op": "resolve", "device_id": device_id}, socket_path)
    if not reply.get("ok"):
        raise BindingClientError(reply.get("error", "resolve failed"))
    return reply["device_id"]


def describe(device_id: str, socket_path: str = DEFAULT_SOCKET) -> list[dict]:
    reply = query({"op": "describe", "device_id": device_id}, socket_path)
    if not reply.get("ok"):
        raise BindingClientError(reply.get("error", "describe failed"))
    return reply["bindings"]


def _print_status(reply: dict) -> None:
    print(f"source     {reply['source']}")
    print(f"loaded     {reply['loaded_at']}")
    print(f"bindings   {reply['bindings']}")
    print(f"protocols  {', '.join(reply['protocols'])}")
    print(f"devices    {', '.join(reply['devices'])}")
    if reply["aliases"]:
        print("aliases")
        for alias, canonical in sorted(reply["aliases"].items()):
            print(f"           {alias} -> {canonical}")


PROTOCOL_FIELDS = {
    "modbus": (
        "register_address",
        "register_base",
        "wire_address",
        "register_count",
        "function_code",
        "register_type",
        "word_order",
        "byte_order",
        "slave_id",
    ),
    "opcua": ("node_id", "namespace_index"),
    "mqtt": ("topic", "qos"),
    "rest": ("path", "method"),
}

COMMON_FIELDS = ("unit", "scale_factor", "offset", "poll_interval_ms")


def _print_describe(reply: dict) -> None:
    print(f"device {reply['device_id']}")
    for b in reply["bindings"]:
        protocol = b.get("protocol", "")
        print(f"\n  {b['binding_id']}  [{protocol}]  {b['property_name']}")
        fields = PROTOCOL_FIELDS.get(protocol, ()) + COMMON_FIELDS
        for key in fields:
            value = b.get(key)
            if value in (None, ""):
                continue
            print(f"      {key:<18}{value}")
        aliases = b.get("device_aliases") or []
        if aliases:
            print(f"      {'aliases':<18}{', '.join(aliases)}")


def _print_read_plan(reply: dict) -> None:
    print(f"protocol {reply['protocol']}")
    print(
        f"{'device':<14}{'property':<16}{'addr':>6}{'fc':>4}"
        f"{'type':>9}{'scale':>9}{'ms':>7}"
    )
    for e in reply["entries"]:
        print(
            f"{e['device_id']:<14}{e['property_name']:<16}"
            f"{str(e['wire_address']):>6}{str(e['function_code']):>4}"
            f"{e['register_type']:>9}{e['scale_factor']:>9}{e['poll_interval_ms']:>7}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="sf-binding",
        description="Query the XA-202606 binding service over its Unix socket.",
    )
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    parser.add_argument("--json", action="store_true", help="raw JSON output")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="service status and loaded ontology")
    sub.add_parser("devices", help="list canonical device ids")
    sub.add_parser("reload", help="re-read bindings.ttl")

    p = sub.add_parser("resolve", help="map a reported id to its canonical id")
    p.add_argument("device_id")

    p = sub.add_parser("describe", help="all bindings for one device")
    p.add_argument("device_id")

    p = sub.add_parser("read-plan", help="polling plan for one protocol")
    p.add_argument("protocol", nargs="?", default="modbus")
    p.add_argument("--device", default="")

    p = sub.add_parser("adapter", help="print generated adapter source")
    p.add_argument("protocol")

    args = parser.parse_args()

    requests = {
        "status": {"op": "status"},
        "devices": {"op": "devices"},
        "reload": {"op": "reload"},
        "resolve": {"op": "resolve", "device_id": getattr(args, "device_id", "")},
        "describe": {"op": "describe", "device_id": getattr(args, "device_id", "")},
        "read-plan": {
            "op": "read_plan",
            "protocol": getattr(args, "protocol", "modbus"),
            "device_id": getattr(args, "device", ""),
        },
        "adapter": {"op": "adapter", "protocol": getattr(args, "protocol", "")},
    }

    try:
        reply = query(requests[args.command], args.socket)
    except BindingClientError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(reply, ensure_ascii=False, indent=2))
        return 0 if reply.get("ok") else 1

    if not reply.get("ok"):
        print(f"error: {reply.get('error')}", file=sys.stderr)
        return 1

    if args.command == "status":
        _print_status(reply)
    elif args.command == "devices":
        print("\n".join(reply["devices"]))
    elif args.command == "resolve":
        arrow = " (alias)" if reply["aliased"] else ""
        print(f"{reply['reported']} -> {reply['device_id']}{arrow}")
    elif args.command == "describe":
        _print_describe(reply)
    elif args.command == "read-plan":
        _print_read_plan(reply)
    elif args.command == "adapter":
        print(reply["source"])
    elif args.command == "reload":
        print(f"reloaded {reply['bindings']} bindings, {len(reply['devices'])} devices")
    return 0


if __name__ == "__main__":
    sys.exit(main())