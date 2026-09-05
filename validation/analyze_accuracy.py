"""Calculate sensor error metrics from DUT/reference paired observations."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

REQUIRED_FIELDS = {
    "timestamp",
    "device_id",
    "measurement_type",
    "dut_value",
    "reference_value",
    "unit",
}


def metrics(pairs: list[tuple[float, float]]) -> dict[str, float | int]:
    if not pairs:
        raise ValueError("at least one pair is required")
    errors = [dut - reference for dut, reference in pairs]
    return {
        "samples": len(errors),
        "bias": statistics.fmean(errors),
        "mae": statistics.fmean(abs(error) for error in errors),
        "rmse": math.sqrt(statistics.fmean(error * error for error in errors)),
        "max_absolute_error": max(abs(error) for error in errors),
    }


def analyze(path: Path) -> dict:
    grouped: dict[tuple[str, str, str], list[tuple[float, float]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_FIELDS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing CSV fields: {sorted(missing)}")
        for row in reader:
            key = (row["device_id"], row["measurement_type"], row["unit"])
            grouped[key].append((float(row["dut_value"]), float(row["reference_value"])))
    if not grouped:
        raise ValueError("CSV has no observations")
    return {
        "evidence_type": "paired_physical_measurement",
        "source": str(path),
        "groups": [
            {
                "device_id": key[0],
                "measurement_type": key[1],
                "unit": key[2],
                **metrics(values),
            }
            for key, values in sorted(grouped.items())
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = analyze(args.csv_file)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
