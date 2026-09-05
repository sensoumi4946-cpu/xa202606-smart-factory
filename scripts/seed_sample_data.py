"""Validate and submit the five synthetic demonstration records."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path

try:
    from scripts.validate_sample_data import (
        DEFAULT_BINDINGS,
        DEFAULT_DATA,
        validate_file,
    )
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    from validate_sample_data import DEFAULT_BINDINGS, DEFAULT_DATA, validate_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--bindings", type=Path, default=DEFAULT_BINDINGS)
    parser.add_argument(
        "--url", default="http://localhost:8000/ingest/api/v1/data"
    )
    parser.add_argument("--api-key", default=os.getenv("API_KEY", ""))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    results = validate_file(args.data, args.bindings)
    failures = [result for result in results if result.errors]
    if failures:
        for result in failures:
            print(f"{result.device_id}: {'; '.join(result.errors)}")
        return 1
    if args.dry_run:
        print(f"validated {len(results)} synthetic demonstration records")
        return 0
    if not args.api_key:
        raise SystemExit("API_KEY or --api-key is required")

    for raw_line in args.data.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        body = raw_line.encode("utf-8")
        device_id = json.loads(raw_line)["device_id"]
        request = urllib.request.Request(
            args.url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-API-Key": args.api_key,
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
        print(f"{device_id}: accepted record={result['record_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
