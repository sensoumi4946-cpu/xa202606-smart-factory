from benchmark import baseline_platform
from benchmark.extensibility_benchmark import (
    measure_baseline_approach,
    measure_semantic_approach,
    run,
)


class TestBaselineIsFair:
    def test_baseline_actually_works(self):
        ok, msg = baseline_platform.validate_reading("temperature", 25.0, "celsius")
        assert ok and msg == "ok"

    def test_baseline_catches_bad_units(self):
        ok, msg = baseline_platform.validate_reading("temperature", 25.0, "fahrenheit")
        assert not ok and "unit" in msg

    def test_baseline_catches_out_of_range(self):
        ok, _ = baseline_platform.validate_reading("temperature", 500.0, "celsius")
        assert not ok

    def test_baseline_evaluates_thresholds(self):
        assert baseline_platform.evaluate_threshold("co", 50.0) == "co_warning"
        assert baseline_platform.evaluate_threshold("co", 5.0) is None

    def test_baseline_supports_all_five_subsystems(self):
        for prop in ("temperature", "co", "distance", "count", "occupancy"):
            assert prop in baseline_platform.SUPPORTED_PROPERTIES

    def test_baseline_rejects_the_new_sensor_before_extension(self):
        ok, msg = baseline_platform.validate_reading("vibration", 3.0, "mm_per_sec")
        assert not ok
        assert "unknown property" in msg


class TestMeasurement:
    def test_ontology_only_does_not_extend_the_runtime_contract(self):
        cost = measure_semantic_approach()
        assert cost.ontology_only_supported is False
        assert cost.restart_required is True

    def test_semantic_keeps_validation(self):
        cost = measure_semantic_approach()
        assert cost.validation_kept is True

    def test_baseline_is_labelled_as_illustrative(self):
        cost = measure_baseline_approach()
        assert cost.restart_required is True
        assert "not a measured external" in cost.notes

    def test_semantic_extension_is_fast(self):
        cost = measure_semantic_approach()
        assert cost.elapsed_seconds < 5.0

    def test_result_reports_the_real_extensibility_boundary(self):
        result = run()
        s = result["summary"]
        assert s["ontology_only_supported"] is False
        assert s["validation_rejects_unknown_type"] is True

    def test_result_is_json_serialisable(self):
        import json

        json.dumps(run())
