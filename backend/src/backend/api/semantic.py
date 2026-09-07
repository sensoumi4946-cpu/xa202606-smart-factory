import asyncio
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from backend import config
from semantic_layer.mapping import SUBSYSTEM_TO_RESOURCE, TYPE_TO_PROPERTY

router = APIRouter()

_TIMEOUT = 8.0
_CACHE_TTL = 60.0
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_inflight: dict[str, asyncio.Task[list[dict[str, Any]]]] = {}

_PREFIX = (
    "PREFIX sosa: <http://www.w3.org/ns/sosa/> "
    "PREFIX sf: <http://example.org/smart-factory#> "
)

_BASE_QUERY = (
    _PREFIX + "SELECT DISTINCT ?sensor ?subsystem ?protocol ?prop WHERE { "
    "?obs a sosa:Observation ; sosa:madeBySensor ?sensor ; "
    "sosa:observedProperty ?prop . "
    "OPTIONAL { ?sensor sf:belongsToSubsystem ?subsystem } "
    "OPTIONAL { ?sensor sf:transportedVia ?protocol } "
    "%s } LIMIT 100"
)

_CO_TEMP_FILTER = (
    "{ SELECT DISTINCT ?sensor WHERE { "
    "?fo sosa:madeBySensor ?sensor ; sosa:observedProperty ?fp . "
    "VALUES ?fp { sf:measuresCO sf:measuresTemperature } } }"
)

_FIRE_RISK_FILTER = (
    "VALUES ?prop { "
    "sf:measuresTemperature sf:measuresCO "
    "sf:measuresSmoke sf:measuresCombustibleGas }"
)

_GAS_DETAIL_FILTER = "?sensor sf:belongsToSubsystem sf:GasMonitoringSubsystem ."

_PRODUCTION_FILTER = (
    "VALUES ?prop { "
    "sf:measuresDistance sf:measuresCount "
    "sf:measuresOccupancy sf:measuresLightState }"
)

VIEWS: dict[str, str] = {
    "sensor-observations": _BASE_QUERY % "",
    "co-temp-sensors": _BASE_QUERY % _CO_TEMP_FILTER,
    "fire-risk-sensors": _BASE_QUERY % _FIRE_RISK_FILTER,
    "gas-subsystem-detail": _BASE_QUERY % _GAS_DETAIL_FILTER,
    "production-sensors": _BASE_QUERY % _PRODUCTION_FILTER,
}

DESCRIPTIONS: dict[str, str] = {
    "sensor-observations": "All sensors with their observed properties and subsystems",
    "co-temp-sensors": "Sensors observing CO or temperature — cross-device fire risk correlation",
    "fire-risk-sensors": "All fire-safety sensors (temperature + CO + smoke + combustible gas) across all protocols",
    "gas-subsystem-detail": "Gas monitoring subsystem: all three hazardous-gas properties via Modbus TCP",
    "production-sensors": "Production-floor sensors: AGV distance (OPC UA), counting (REST), occupancy/lighting (REST)",
}


def _local(uri: str) -> str:
    return uri.rsplit("#", 1)[-1] if "#" in uri else uri.rsplit("/", 1)[-1]


PROP_NAMES: dict[str, str] = {
    _local(str(uri)): mtype.value for mtype, uri in TYPE_TO_PROPERTY.items()
}
SUBSYS_NAMES: dict[str, str] = {
    _local(str(uri)): sub.value for sub, uri in SUBSYSTEM_TO_RESOURCE.items()
}


async def _run_sparql(query: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=_TIMEOUT, trust_env=False) as client:
        resp = await client.post(
            config.FUSEKI_QUERY_URL,
            content=query.encode("utf-8"),
            headers={
                "Content-Type": "application/sparql-query",
                "Accept": "application/sparql-results+json",
            },
        )
    resp.raise_for_status()
    return resp.json()["results"]["bindings"]


async def _cached_sparql(view: str) -> list[dict[str, Any]]:
    cached = _cache.get(view)
    now = time.monotonic()
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]
    task = _inflight.get(view)
    if task is None:
        task = asyncio.create_task(_run_sparql(VIEWS[view]))
        _inflight[view] = task
    try:
        bindings = await task
        _cache[view] = (time.monotonic(), bindings)
        return bindings
    finally:
        if _inflight.get(view) is task:
            _inflight.pop(view, None)


def _aggregate(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order: list[str] = []
    by_sensor: dict[str, dict[str, Any]] = {}
    for b in bindings:
        sensor = _local(b["sensor"]["value"])
        if sensor not in by_sensor:
            subsys = _local(b["subsystem"]["value"]) if "subsystem" in b else ""
            by_sensor[sensor] = {
                "sensor": sensor,
                "subsystem": SUBSYS_NAMES.get(subsys, subsys),
                "observes": [],
                "protocol": b.get("protocol", {}).get("value", ""),
            }
            order.append(sensor)
        if "prop" in b:
            prop = PROP_NAMES.get(_local(b["prop"]["value"]))
            if prop and prop not in by_sensor[sensor]["observes"]:
                by_sensor[sensor]["observes"].append(prop)
    return [by_sensor[s] for s in order]


def _binding_fallback(view: str) -> list[dict[str, Any]]:
    from backend.api.innovation_api import binding_registry

    allowed_properties = {
        "temperature", "humidity", "count", "occupancy", "light_state",
        "distance", "co", "smoke", "combustible_gas",
    }
    view_properties = {
        "co-temp-sensors": {"co", "temperature"},
        "fire-risk-sensors": {
            "temperature", "co", "smoke", "combustible_gas"
        },
        "production-sensors": {
            "distance", "count", "occupancy", "light_state"
        },
    }

    grouped: dict[str, dict[str, Any]] = {}
    for binding in binding_registry.all():
        prop = binding.property_name
        subsystem = binding.canonical_subsystem

        if prop not in allowed_properties:
            continue
        if view == "gas-subsystem-detail" and subsystem != "gas":
            continue
        if view in view_properties and prop not in view_properties[view]:
            continue

        item = grouped.setdefault(
            binding.device_id,
            {
                "sensor": binding.device_id,
                "subsystem": subsystem,
                "observes": [],
                "_protocols": set(),
            },
        )
        if prop not in item["observes"]:
            item["observes"].append(prop)
        item["_protocols"].add(binding.protocol)

    results = []
    for item in grouped.values():
        protocols = sorted(item.pop("_protocols"))
        item["protocol"] = ", ".join(protocols)
        item["observes"].sort()
        results.append(item)

    return sorted(results, key=lambda item: item["sensor"])


@router.get("/api/v1/semantic")
async def semantic(view: Optional[str] = Query(None)):
    if view not in VIEWS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown view '{view}'. Valid options: {sorted(VIEWS.keys())}",
        )
    try:
        bindings = await _cached_sparql(view)
    except httpx.HTTPError:
        return {
            "view": view,
            "description": DESCRIPTIONS[view],
            "results": _binding_fallback(view),
            "degraded": True,
            "reason": "Fuseki 查询超时，已使用本体协议绑定快照",
        }

    results = _aggregate(bindings)
    if not results:
        return {
            "view": view,
            "description": DESCRIPTIONS[view],
            "results": _binding_fallback(view),
            "degraded": True,
            "reason": "Fuseki 查询无结果，已使用本体协议绑定快照",
        }

    return {
        "view": view,
        "description": DESCRIPTIONS[view],
        "results": results,
        "degraded": False,
    }
