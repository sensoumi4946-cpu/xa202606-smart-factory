#!/usr/bin/env python3
"""Generate or verify checked-in protocol adapters from bindings.ttl."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from semantic_layer.protocol_binding import BindingRegistry, generate_all


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bindings", type=Path, default=Path("bindings.ttl"))
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = BindingRegistry()
    result = registry.load_turtle(args.bindings.read_text(encoding="utf-8"))
    if not result.accepted:
        print("bindings rejected: " + "; ".join(result.violations), file=sys.stderr)
        return 2

    stale: list[str] = []
    for protocol, source in generate_all(registry).items():
        target = args.output_dir / f"generated_{protocol}_adapter.py"
        if args.check:
            if not target.exists() or target.read_text(encoding="utf-8") != source:
                stale.append(str(target))
            continue
        target.write_text(source, encoding="utf-8")
        print(f"generated {target}")

    if stale:
        print("stale generated adapters: " + ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
