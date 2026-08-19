import pytest

from semantic_layer.privacy_federation import (
    QUANTILES,
    PrivacyBudget,
    PrivacyBudgetExceeded,
    StatisticalSummary,
    StatisticsExchange,
    benchmark,
    summarise,
    summary_fingerprint,
)


def readings(base: float, n: int = 100, step: float = 0.1) -> list[float]:
    return [base + i * step for i in range(n)]


class TestSuppression:
    def test_small_sample_is_suppressed(self):
        s = summarise("site_a", "temperature", readings(20.0, 5), sensitivity=1.0)
        assert s.suppressed
        assert s.mean == 0.0
        assert "k-anonymity" in s.reason

    def test_sample_at_threshold_is_released(self):
        s = summarise("site_a", "temperature", readings(20.0, 20), sensitivity=1.0)
        assert not s.suppressed

    def test_suppressed_summary_leaks_nothing(self):
        s = summarise("site_a", "temperature", [99.9] * 3, sensitivity=1.0)
        assert s.mean == 0.0
        assert s.std == 0.0
        assert s.quantiles == {}


class TestNoRawData:
    def test_summary_has_no_reading_list(self):
        s = summarise("site_a", "temperature", readings(20.0), sensitivity=1.0)
        payload = s.to_dict()
        assert "values" not in payload
        assert "readings" not in payload
        assert not s.contains_raw_readings()

    def test_payload_size_is_independent_of_sample_count(self):
        small = summarise("s", "temperature", readings(20.0, 25), sensitivity=1.0, seed=7)
        large = summarise("s", "temperature", readings(20.0, 5000), sensitivity=1.0, seed=7)
        assert set(small.to_dict()) == set(large.to_dict())
        assert len(small.quantiles) == len(large.quantiles)

    def test_payload_holds_no_collection_of_readings(self):
        values = readings(20.0, 500)
        payload = summarise("s", "temperature", values, sensitivity=1.0, seed=7).to_dict()
        for key, value in payload.items():
            assert not isinstance(value, (list, tuple)), key
            if isinstance(value, dict):
                assert len(value) <= len(QUANTILES)

    def test_only_aggregate_keys_are_exported(self):
        s = summarise("site_a", "temperature", readings(20.0), sensitivity=1.0)
        allowed = {
            "site_id",
            "canonical_property",
            "sample_count",
            "mean",
            "std",
            "quantiles",
            "anomaly_rate",
            "threshold_breaches",
            "epsilon",
            "suppressed",
            "reason",
            "window_start",
            "window_end",
        }
        assert set(s.to_dict()) == allowed


class TestNoise:
    def test_noise_is_applied(self):
        values = readings(20.0, 100)
        exact = sum(values) / len(values)
        s = summarise("site_a", "temperature", values, sensitivity=1.0, seed=1)
        assert s.mean != exact

    def test_noise_is_reproducible_with_a_seed(self):
        values = readings(20.0, 100)
        a = summarise("s", "temperature", values, sensitivity=1.0, seed=42)
        b = summarise("s", "temperature", values, sensitivity=1.0, seed=42)
        assert a.mean == b.mean

    def test_different_seeds_give_different_noise(self):
        values = readings(20.0, 100)
        a = summarise("s", "temperature", values, sensitivity=1.0, seed=1)
        b = summarise("s", "temperature", values, sensitivity=1.0, seed=2)
        assert a.mean != b.mean

    def test_noise_stays_useful(self):
        values = readings(20.0, 200)
        exact = sum(values) / len(values)
        s = summarise("s", "temperature", values, sensitivity=1.0, seed=3)
        assert abs(s.mean - exact) < 2.0

    def test_smaller_epsilon_adds_more_noise(self):
        values = readings(20.0, 100)
        exact = sum(values) / len(values)
        loose = summarise("s", "t", values, sensitivity=1.0, epsilon=5.0, seed=9)
        tight = summarise("s", "t", values, sensitivity=1.0, epsilon=0.05, seed=9)
        assert abs(tight.mean - exact) > abs(loose.mean - exact)

    def test_quantiles_are_reported(self):
        s = summarise("s", "temperature", readings(20.0, 100), sensitivity=1.0, seed=1)
        assert set(s.quantiles) == {"p5", "p25", "p50", "p75", "p95"}

    def test_anomaly_rate_bounded(self):
        flags = [True] * 50 + [False] * 50
        s = summarise(
            "s", "co", readings(30.0, 100), sensitivity=1.0, anomaly_flags=flags, seed=5
        )
        assert 0.0 <= s.anomaly_rate <= 1.0

    def test_threshold_breaches_counted(self):
        values = [10.0] * 50 + [90.0] * 50
        s = summarise("s", "co", values, sensitivity=1.0, threshold=50.0, seed=5)
        assert s.threshold_breaches > 20


class TestBudget:
    def test_budget_starts_full(self):
        assert PrivacyBudget(10.0).remaining("a") == 10.0

    def test_spending_reduces_budget(self):
        b = PrivacyBudget(10.0)
        b.spend("a", 3.0)
        assert b.remaining("a") == pytest.approx(7.0)

    def test_overspending_raises(self):
        b = PrivacyBudget(1.0)
        with pytest.raises(PrivacyBudgetExceeded):
            b.spend("a", 2.0)

    def test_budgets_are_per_site(self):
        b = PrivacyBudget(2.0)
        b.spend("a", 2.0)
        assert b.remaining("b") == 2.0

    def test_exchange_spends_budget_on_publish(self):
        ex = StatisticsExchange(PrivacyBudget(5.0))
        ex.publish("a", "temperature", readings(20.0), sensitivity=1.0, epsilon=1.0)
        assert ex.budget.spent("a") == pytest.approx(1.0)

    def test_suppressed_publish_costs_nothing(self):
        ex = StatisticsExchange(PrivacyBudget(5.0))
        ex.publish("a", "temperature", [1.0, 2.0], sensitivity=1.0, epsilon=1.0)
        assert ex.budget.spent("a") == 0.0

    def test_exhausted_budget_blocks_further_publishing(self):
        ex = StatisticsExchange(PrivacyBudget(1.5))
        ex.publish("a", "temperature", readings(20.0), sensitivity=1.0, epsilon=1.0)
        with pytest.raises(PrivacyBudgetExceeded):
            ex.publish("a", "co", readings(30.0), sensitivity=1.0, epsilon=1.0)


class TestBenchmark:
    def _summaries(self):
        own = summarise("mine", "co", readings(45.0, 100), sensitivity=1.0, seed=1)
        peers = [
            summarise("p1", "co", readings(20.0, 100), sensitivity=1.0, seed=2),
            summarise("p2", "co", readings(21.0, 100), sensitivity=1.0, seed=3),
            summarise("p3", "co", readings(19.0, 100), sensitivity=1.0, seed=4),
        ]
        return own, peers

    def test_outlier_detected_without_sharing_readings(self):
        own, peers = self._summaries()
        position = benchmark(own, peers)
        assert position is not None
        assert position.verdict == "high_outlier"
        assert position.peer_count == 3

    def test_typical_site_reported_as_typical(self):
        own = summarise("mine", "co", readings(20.2, 100), sensitivity=1.0, seed=1)
        peers = [
            summarise("p1", "co", readings(20.0, 100), sensitivity=1.0, seed=2),
            summarise("p2", "co", readings(25.0, 100), sensitivity=1.0, seed=3),
            summarise("p3", "co", readings(15.0, 100), sensitivity=1.0, seed=4),
        ]
        assert benchmark(own, peers).verdict == "typical"

    def test_low_outlier_flagged_as_possible_sensor_fault(self):
        own = summarise("mine", "co", readings(1.0, 100), sensitivity=1.0, seed=1)
        peers = [
            summarise("p1", "co", readings(40.0, 100), sensitivity=1.0, seed=2),
            summarise("p2", "co", readings(41.0, 100), sensitivity=1.0, seed=3),
            summarise("p3", "co", readings(39.0, 100), sensitivity=1.0, seed=4),
        ]
        position = benchmark(own, peers)
        assert position.verdict == "low_outlier"
        assert "传感器" in position.advice_zh

    def test_percentile_reported(self):
        own, peers = self._summaries()
        assert benchmark(own, peers).percentile == 100.0

    def test_suppressed_own_summary_gives_no_position(self):
        own = summarise("mine", "co", [1.0, 2.0], sensitivity=1.0)
        _, peers = self._summaries()
        assert benchmark(own, peers) is None

    def test_no_peers_gives_no_position(self):
        own, _ = self._summaries()
        assert benchmark(own, []) is None

    def test_suppressed_peers_are_excluded(self):
        own, peers = self._summaries()
        peers.append(summarise("p4", "co", [1.0], sensitivity=1.0))
        assert benchmark(own, peers).peer_count == 3

    def test_own_summary_not_counted_as_peer(self):
        own, peers = self._summaries()
        assert benchmark(own, peers + [own]).peer_count == 3

    def test_advice_is_chinese(self):
        own, peers = self._summaries()
        assert any("\u4e00" <= ch <= "\u9fff" for ch in benchmark(own, peers).advice_zh)


class TestExchange:
    def test_position_after_publishing(self):
        ex = StatisticsExchange(PrivacyBudget(50.0))
        ex.publish("mine", "co", readings(45.0, 100), sensitivity=1.0, seed=1)
        ex.publish("p1", "co", readings(20.0, 100), sensitivity=1.0, seed=2)
        ex.publish("p2", "co", readings(21.0, 100), sensitivity=1.0, seed=3)
        position = ex.position_of("mine", "co")
        assert position is not None
        assert position.verdict == "high_outlier"

    def test_published_filters_by_property(self):
        ex = StatisticsExchange(PrivacyBudget(50.0))
        ex.publish("a", "co", readings(20.0), sensitivity=1.0, seed=1)
        ex.publish("a", "temperature", readings(20.0), sensitivity=1.0, seed=1)
        assert len(ex.published("co")) == 1

    def test_unknown_site_has_no_position(self):
        assert StatisticsExchange().position_of("nobody", "co") is None

    def test_reset_clears_everything(self):
        ex = StatisticsExchange(PrivacyBudget(50.0))
        ex.publish("a", "co", readings(20.0), sensitivity=1.0, seed=1)
        ex.reset()
        assert ex.published("co") == []
        assert ex.budget.spent("a") == 0.0

    def test_fingerprint_is_stable(self):
        s = summarise("a", "co", readings(20.0), sensitivity=1.0, seed=1)
        assert summary_fingerprint(s) == summary_fingerprint(s)
