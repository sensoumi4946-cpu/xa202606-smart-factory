import csv

import pytest

from validation.analyze_accuracy import analyze, metrics
from validation.measure_ingest_performance import percentile, summarize


def test_percentile_uses_nearest_rank():
    assert percentile([5, 1, 4, 2, 3], 50) == 3
    assert percentile([5, 1, 4, 2, 3], 95) == 5


def test_performance_summary():
    report = summarize([10.0, 20.0], errors=1, elapsed_s=0.5)
    assert report["requests"] == 3
    assert report["throughput_rps"] == 4.0
    assert report["error_rate"] == pytest.approx(1 / 3)


def test_accuracy_metrics():
    report = metrics([(10.0, 9.0), (8.0, 9.0)])
    assert report == {
        "samples": 2,
        "bias": 0.0,
        "mae": 1.0,
        "rmse": 1.0,
        "max_absolute_error": 1.0,
    }


def test_analyze_groups_csv(tmp_path):
    path = tmp_path / "accuracy.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "timestamp",
                "device_id",
                "measurement_type",
                "dut_value",
                "reference_value",
                "unit",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "device_id": "ESP32_001",
                "measurement_type": "temperature",
                "dut_value": "26.5",
                "reference_value": "26.0",
                "unit": "celsius",
            }
        )
    report = analyze(path)
    assert report["groups"][0]["mae"] == 0.5
