from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

MIN_SAMPLES = 20
DEFAULT_EPSILON = 1.0
DEFAULT_BUDGET = 10.0
QUANTILES = (0.05, 0.25, 0.50, 0.75, 0.95)


class PrivacyBudgetExceeded(Exception):
    pass


@dataclass
class StatisticalSummary:
    site_id: str
    canonical_property: str
    sample_count: int
    mean: float
    std: float
    quantiles: dict[str, float]
    anomaly_rate: float
    threshold_breaches: int
    epsilon: float
    suppressed: bool = False
    reason: str = ""
    window_start: float = 0.0
    window_end: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "canonical_property": self.canonical_property,
            "sample_count": self.sample_count,
            "mean": self.mean,
            "std": self.std,
            "quantiles": self.quantiles,
            "anomaly_rate": self.anomaly_rate,
            "threshold_breaches": self.threshold_breaches,
            "epsilon": self.epsilon,
            "suppressed": self.suppressed,
            "reason": self.reason,
            "window_start": self.window_start,
            "window_end": self.window_end,
        }

    def contains_raw_readings(self) -> bool:
        return False


@dataclass
class BenchmarkPosition:
    site_id: str
    canonical_property: str
    own_mean: float
    network_mean: float
    network_std: float
    z_score: float
    percentile: float
    peer_count: int
    verdict: str
    advice_zh: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "canonical_property": self.canonical_property,
            "own_mean": round(self.own_mean, 3),
            "network_mean": round(self.network_mean, 3),
            "network_std": round(self.network_std, 3),
            "z_score": round(self.z_score, 3),
            "percentile": round(self.percentile, 1),
            "peer_count": self.peer_count,
            "verdict": self.verdict,
            "advice_zh": self.advice_zh,
        }


class PrivacyBudget:
    def __init__(self, total: float = DEFAULT_BUDGET) -> None:
        self.total = total
        self._spent: dict[str, float] = {}

    def spend(self, site_id: str, epsilon: float) -> None:
        used = self._spent.get(site_id, 0.0)
        if used + epsilon > self.total:
            raise PrivacyBudgetExceeded(
                f"site {site_id} would spend {used + epsilon:.2f} of {self.total:.2f}"
            )
        self._spent[site_id] = used + epsilon

    def remaining(self, site_id: str) -> float:
        return self.total - self._spent.get(site_id, 0.0)

    def spent(self, site_id: str) -> float:
        return self._spent.get(site_id, 0.0)

    def reset(self) -> None:
        self._spent.clear()


def _laplace(scale: float, rng: random.Random) -> float:
    if scale <= 0:
        return 0.0
    u = rng.random() - 0.5
    return -scale * math.copysign(1.0, u) * math.log(1 - 2 * abs(u))


def _quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    position = q * (len(sorted_values) - 1)
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return sorted_values[low]
    weight = position - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


def summarise(
    site_id: str,
    canonical_property: str,
    values: list[float],
    sensitivity: float,
    anomaly_flags: Optional[list[bool]] = None,
    threshold: Optional[float] = None,
    epsilon: float = DEFAULT_EPSILON,
    min_samples: int = MIN_SAMPLES,
    seed: Optional[int] = None,
    window_start: float = 0.0,
    window_end: float = 0.0,
) -> StatisticalSummary:
    if len(values) < min_samples:
        return StatisticalSummary(
            site_id=site_id,
            canonical_property=canonical_property,
            sample_count=len(values),
            mean=0.0,
            std=0.0,
            quantiles={},
            anomaly_rate=0.0,
            threshold_breaches=0,
            epsilon=0.0,
            suppressed=True,
            reason=f"fewer than {min_samples} samples — suppressed for k-anonymity",
            window_start=window_start,
            window_end=window_end,
        )

    rng = random.Random(seed)
    n = len(values)
    ordered = sorted(values)

    raw_mean = sum(values) / n
    variance = sum((v - raw_mean) ** 2 for v in values) / n
    raw_std = math.sqrt(variance)

    per_statistic = epsilon / (2 + len(QUANTILES))
    mean_scale = sensitivity / (n * per_statistic)

    noisy_mean = raw_mean + _laplace(mean_scale, rng)
    noisy_std = max(0.0, raw_std + _laplace(mean_scale, rng))

    noisy_quantiles = {}
    for q in QUANTILES:
        value = _quantile(ordered, q)
        noisy_quantiles[f"p{int(q * 100)}"] = round(
            value + _laplace(sensitivity / (n * per_statistic), rng), 4
        )

    if anomaly_flags:
        raw_rate = sum(1 for flag in anomaly_flags if flag) / len(anomaly_flags)
    else:
        raw_rate = 0.0
    noisy_rate = min(1.0, max(0.0, raw_rate + _laplace(1.0 / (n * per_statistic), rng)))

    breaches = (
        sum(1 for v in values if v > threshold) if threshold is not None else 0
    )
    noisy_breaches = max(0, int(round(breaches + _laplace(1.0 / per_statistic, rng))))

    return StatisticalSummary(
        site_id=site_id,
        canonical_property=canonical_property,
        sample_count=n,
        mean=round(noisy_mean, 4),
        std=round(noisy_std, 4),
        quantiles=noisy_quantiles,
        anomaly_rate=round(noisy_rate, 4),
        threshold_breaches=noisy_breaches,
        epsilon=epsilon,
        window_start=window_start,
        window_end=window_end,
    )


def summary_fingerprint(summary: StatisticalSummary) -> str:
    payload = (
        f"{summary.site_id}|{summary.canonical_property}|{summary.sample_count}"
        f"|{summary.mean}|{summary.std}|{summary.epsilon}"
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def benchmark(
    own: StatisticalSummary, peers: list[StatisticalSummary]
) -> Optional[BenchmarkPosition]:
    usable = [p for p in peers if not p.suppressed and p.site_id != own.site_id]
    if own.suppressed or not usable:
        return None

    peer_means = [p.mean for p in usable]
    network_mean = sum(peer_means) / len(peer_means)

    if len(peer_means) > 1:
        variance = sum((m - network_mean) ** 2 for m in peer_means) / (
            len(peer_means) - 1
        )
        network_std = math.sqrt(variance)
    else:
        network_std = 0.0

    denominator = max(network_std, 1e-6)
    z = (own.mean - network_mean) / denominator

    below = sum(1 for m in peer_means if m < own.mean)
    percentile = 100.0 * below / len(peer_means)

    if abs(z) < 1.0:
        verdict = "typical"
        advice = "与同行水平相当，暂无需调整。"
    elif z >= 2.0:
        verdict = "high_outlier"
        advice = "明显高于同行平均，建议排查设备状态或工艺参数。"
    elif z >= 1.0:
        verdict = "above_peers"
        advice = "略高于同行平均，建议持续观察。"
    elif z <= -2.0:
        verdict = "low_outlier"
        advice = "明显低于同行平均，可能是传感器失效或标定偏移。"
    else:
        verdict = "below_peers"
        advice = "略低于同行平均，可作为标杆经验沉淀。"

    return BenchmarkPosition(
        site_id=own.site_id,
        canonical_property=own.canonical_property,
        own_mean=own.mean,
        network_mean=network_mean,
        network_std=network_std,
        z_score=z,
        percentile=percentile,
        peer_count=len(usable),
        verdict=verdict,
        advice_zh=advice,
    )


class StatisticsExchange:
    def __init__(
        self,
        budget: Optional[PrivacyBudget] = None,
        min_samples: int = MIN_SAMPLES,
        timeout: float = 8.0,
    ) -> None:
        self.budget = budget if budget is not None else PrivacyBudget()
        self.min_samples = min_samples
        self.timeout = timeout
        self._published: dict[tuple[str, str], StatisticalSummary] = {}

    def reset(self) -> None:
        self.budget.reset()
        self._published.clear()

    def publish(
        self,
        site_id: str,
        canonical_property: str,
        values: list[float],
        sensitivity: float,
        anomaly_flags: Optional[list[bool]] = None,
        threshold: Optional[float] = None,
        epsilon: float = DEFAULT_EPSILON,
        seed: Optional[int] = None,
    ) -> StatisticalSummary:
        summary = summarise(
            site_id=site_id,
            canonical_property=canonical_property,
            values=values,
            sensitivity=sensitivity,
            anomaly_flags=anomaly_flags,
            threshold=threshold,
            epsilon=epsilon,
            min_samples=self.min_samples,
            seed=seed,
            window_end=time.time(),
        )
        if not summary.suppressed:
            self.budget.spend(site_id, epsilon)
            self._published[(site_id, canonical_property)] = summary
        return summary

    def published(self, canonical_property: str) -> list[StatisticalSummary]:
        return [
            s
            for (site, prop), s in self._published.items()
            if prop == canonical_property
        ]

    def position_of(self, site_id: str, canonical_property: str):
        own = self._published.get((site_id, canonical_property))
        if own is None:
            return None
        peers = self.published(canonical_property)
        return benchmark(own, peers)

    async def collect(
        self,
        sites: list[Any],
        canonical_property: str,
        client: Optional[httpx.AsyncClient] = None,
    ) -> list[StatisticalSummary]:
        owns = client is None
        client = client or httpx.AsyncClient()

        async def fetch(site) -> Optional[StatisticalSummary]:
            url = site.sparql_endpoint.rsplit("/", 1)[0] + "/api/v1/federation/statistics"
            assert client is not None
            try:
                response = await client.get(
                    url,
                    params={"property": canonical_property},
                    timeout=self.timeout,
                )
                if response.status_code != 200:
                    return None
                body = response.json()
                return StatisticalSummary(
                    site_id=body.get("site_id", site.site_id),
                    canonical_property=body.get(
                        "canonical_property", canonical_property
                    ),
                    sample_count=int(body.get("sample_count", 0)),
                    mean=float(body.get("mean", 0.0)),
                    std=float(body.get("std", 0.0)),
                    quantiles=body.get("quantiles", {}),
                    anomaly_rate=float(body.get("anomaly_rate", 0.0)),
                    threshold_breaches=int(body.get("threshold_breaches", 0)),
                    epsilon=float(body.get("epsilon", 0.0)),
                    suppressed=bool(body.get("suppressed", False)),
                    reason=str(body.get("reason", "")),
                )
            except Exception as exc:
                logger.warning("statistics fetch failed for %s: %s", site.site_id, exc)
                return None

        try:
            results = await asyncio.gather(*(fetch(s) for s in sites))
        finally:
            if owns:
                assert client is not None
                await client.aclose()

        return [r for r in results if r is not None]


exchange = StatisticsExchange()
