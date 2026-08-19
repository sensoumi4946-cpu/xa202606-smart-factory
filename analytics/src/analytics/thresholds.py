from __future__ import annotations

import logging
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

FALLBACK_LIMITS: dict[str, tuple[float, float]] = {
    "temperature": (-40.0, 80.0),
    "humidity": (0.0, 100.0),
    "co": (0.0, 1000.0),
    "smoke": (0.0, 1000.0),
    "combustible_gas": (0.0, 1000.0),
    "distance": (0.0, 450.0),
    "count": (0.0, 1_000_000.0),
    "occupancy": (0.0, 1.0),
    "light_state": (0.0, 1.0),
}

FALLBACK_THRESHOLDS: dict[str, tuple[float, str]] = {
    "temperature": (38.0, "above"),
    "co": (35.0, "above"),
    "smoke": (8.0, "above"),
    "combustible_gas": (3.0, "above"),
    "humidity": (85.0, "above"),
    "distance": (30.0, "below"),
}

FALLBACK_WARN: dict[str, float] = {
    "temperature": 30.0,
    "co": 20.0,
    "smoke": 5.0,
    "combustible_gas": 2.0,
    "humidity": 80.0,
    "distance": 60.0,
}


class ThresholdResolver:

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._registry: Any = None
        self._version: str = "fallback"

    def bind(self, registry: Any) -> None:
        with self._lock:
            self._registry = registry
        logger.info("threshold resolver bound to meta-model registry")

    def unbind(self) -> None:
        with self._lock:
            self._registry = None

    @property
    def version(self) -> str:
        with self._lock:
            if self._registry is None:
                return "fallback"
            return getattr(self._registry, "version", "unknown")

    def _ontology_limits(self) -> dict[str, tuple[float, float]]:
        with self._lock:
            if self._registry is None:
                return {}
            try:
                return dict(self._registry.hard_limits())
            except Exception:
                return {}

    DIRECTION_ALIAS = {
        "high": "above",
        "low": "below",
        "above": "above",
        "below": "below",
    }

    def _ontology_thresholds(self) -> dict[str, tuple[float, str]]:
        with self._lock:
            if self._registry is None:
                return {}
            try:
                raw = dict(self._registry.thresholds())
            except Exception:
                return {}
        return {
            name: (float(value), self.DIRECTION_ALIAS.get(str(direction), "above"))
            for name, (value, direction) in raw.items()
        }

    def _ontology_properties(self) -> dict[str, Any]:
        with self._lock:
            if self._registry is None:
                return {}
            try:
                return dict(self._registry.properties())
            except Exception:
                return {}

    def limits(self) -> dict[str, tuple[float, float]]:
        merged = dict(FALLBACK_LIMITS)
        merged.update(self._ontology_limits())
        return merged

    def limit_for(self, property_name: str) -> Optional[tuple[float, float]]:
        return self.limits().get(property_name)

    def thresholds(self) -> dict[str, tuple[float, str]]:
        merged = dict(FALLBACK_THRESHOLDS)
        merged.update(self._ontology_thresholds())
        return merged

    def threshold_for(self, property_name: str) -> Optional[tuple[float, str]]:
        return self.thresholds().get(property_name)

    def warn_for(self, property_name: str) -> Optional[float]:
        props = self._ontology_properties()
        definition = props.get(property_name)
        if definition is not None:
            warn = getattr(definition, "warn_threshold", None)
            if warn is not None:
                return float(warn)
        return FALLBACK_WARN.get(property_name)

    def direction_for(self, property_name: str) -> str:
        threshold = self.threshold_for(property_name)
        return threshold[1] if threshold else "above"

    def known_properties(self) -> list[str]:
        return sorted(set(self.limits()) | set(self._ontology_properties()))

    def resolve_source(self, property_name: str) -> str:
        if property_name in self._ontology_thresholds():
            return "ontology"
        if property_name in self._ontology_limits():
            return "ontology"
        if property_name in FALLBACK_THRESHOLDS or property_name in FALLBACK_LIMITS:
            return "fallback"
        return "unknown"

    def report(self) -> dict[str, Any]:
        ontology_props = set(self._ontology_limits()) | set(self._ontology_thresholds())
        return {
            "ontology_version": self.version,
            "bound": self._registry is not None,
            "from_ontology": sorted(ontology_props),
            "from_fallback": sorted(set(FALLBACK_LIMITS) - ontology_props),
            "total_properties": len(self.known_properties()),
        }


resolver = ThresholdResolver()


def bind_registry(registry: Any) -> None:
    resolver.bind(registry)


def autobind() -> bool:
    try:
        from semantic_layer.meta_model import registry as meta_registry
    except ImportError:
        return False
    resolver.bind(meta_registry)
    return True
