"""

Drop-in: semantic-layer/src/semantic_layer/
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from rdflib import RDF, XSD, Graph, Literal, Namespace, URIRef

logger = logging.getLogger(__name__)

SF = Namespace("http://example.org/smart-factory#")
AAS = Namespace("urn:smart-factory:aas:")
PROV = Namespace("http://www.w3.org/ns/prov#")

_PROPERTY_MAP: dict[str, URIRef] = {
    "temperature": SF.measuresTemperature,
    "humidity": SF.measuresHumidity,
    "smoke": SF.measuresSmoke,
    "co": SF.measuresCO,
    "combustible_gas": SF.measuresCombustibleGas,
    "distance": SF.measuresDistance,
    "count": SF.measuresCount,
    "occupancy": SF.measuresOccupancy,
    "light_state": SF.measuresLightState,
}

_SUBSYSTEM_MAP: dict[str, URIRef] = {
    "temp_humidity": SF.TempHumiditySubsystem,
    "lighting": SF.LightingSubsystem,
    "gas": SF.GasMonitoringSubsystem,
    "agv": SF.AGVObstacleSubsystem,
    "counting": SF.CountingSubsystem,
}


@dataclass
class LiveDevice:
    """Snapshot of a device seen in the ingest pipeline."""

    device_id: str
    subsystem: str
    protocol: str
    measurement_types: list[str]
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def aas_shell_uri(self) -> URIRef:
        return URIRef(f"{AAS}{self.device_id}")

    @property
    def submodel_uri(self) -> URIRef:
        return URIRef(f"{AAS}{self.device_id}:OperationalData")


@dataclass
class RegistryDiff:
    new_devices: list[LiveDevice] = field(default_factory=list)
    retired_ids: list[str] = field(default_factory=list)
    protocol_changed: list[LiveDevice] = field(default_factory=list)


def _device_to_rdf(device: LiveDevice) -> Graph:

    g = Graph()
    g.bind("sf", SF)
    g.bind("aas", AAS)
    g.bind("prov", PROV)

    shell = device.aas_shell_uri
    asset = URIRef(f"{SF}{device.device_id}")
    sub = device.submodel_uri
    now = Literal(datetime.now(timezone.utc).isoformat(), datatype=XSD.dateTime)

    g.add((shell, RDF.type, SF.AssetAdministrationShell))
    g.add((shell, SF.globalAssetId, asset))
    g.add((shell, SF.hasSubmodel, sub))
    g.add((shell, PROV.generatedAtTime, now))
    g.add((shell, SF.registrationSource, Literal("aas_live_sync")))

    g.add((sub, RDF.type, SF.Submodel))
    g.add(
        (sub, SF.semanticId, _SUBSYSTEM_MAP.get(device.subsystem, SF.UnknownSubsystem))
    )
    g.add((sub, SF.subsystem, Literal(device.subsystem)))
    g.add((sub, SF.protocol, Literal(device.protocol)))
    g.add((sub, SF.hasDevice, asset))

    for mt in device.measurement_types:
        prop_uri = _PROPERTY_MAP.get(mt)
        if prop_uri:
            g.add((sub, SF.hasObservableProperty, prop_uri))

    g.add(
        (
            asset,
            SF.belongsToSubsystem,
            _SUBSYSTEM_MAP.get(device.subsystem, SF.UnknownSubsystem),
        )
    )
    g.add((asset, SF.transportedVia, Literal(device.protocol)))

    return g


class AASRegistry:
    def __init__(self) -> None:
        self._known: dict[str, LiveDevice] = {}

    def observe(self, device: LiveDevice) -> bool:

        existing = self._known.get(device.device_id)
        if existing is None:
            self._known[device.device_id] = device
            logger.info("New device registered: %s", device.device_id)
            return True
        if existing.protocol != device.protocol:
            self._known[device.device_id] = device
            logger.info(
                "Protocol changed for %s: %s → %s",
                device.device_id,
                existing.protocol,
                device.protocol,
            )
            return True
        self._known[device.device_id] = device
        return False

    def diff(self, current_ids: set[str]) -> RegistryDiff:
        known_ids = set(self._known.keys())
        return RegistryDiff(
            new_devices=[],
            retired_ids=list(known_ids - current_ids),
        )

    def all_devices(self) -> list[LiveDevice]:
        return list(self._known.values())

    def get(self, device_id: str) -> Optional[LiveDevice]:
        return self._known.get(device_id)


async def register_device_in_fuseki(device: LiveDevice, endpoint: str) -> bool:

    g = _device_to_rdf(device)
    turtle = g.serialize(format="turtle")
    named_graph = f"urn:smart-factory:aas:{device.device_id}"

    url = f"{endpoint}?graph={named_graph}"
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            resp = await client.put(
                url,
                content=turtle.encode("utf-8"),
                headers={"Content-Type": "text/turtle"},
            )
        ok = 200 <= resp.status_code < 300
        if ok:
            logger.info("AAS registered in Fuseki: %s", device.device_id)
        else:
            logger.warning(
                "Fuseki PUT failed %d for %s", resp.status_code, device.device_id
            )
        return ok
    except httpx.HTTPError as exc:
        logger.warning("Fuseki unreachable during AAS registration: %s", exc)
        return False


async def retire_device_in_fuseki(device_id: str, endpoint: str) -> bool:

    named_graph = f"urn:smart-factory:aas:{device_id}"
    url = f"{endpoint}?graph={named_graph}"
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            resp = await client.delete(url)
        ok = resp.status_code in (200, 204, 404)
        logger.info(
            "AAS retired in Fuseki: %s (status %d)", device_id, resp.status_code
        )
        return ok
    except httpx.HTTPError as exc:
        logger.warning("Fuseki unreachable during AAS retirement: %s", exc)
        return False


async def watch_loop(
    registry: AASRegistry,
    fuseki_data_endpoint: str,
    poll_interval_seconds: float = 30.0,
) -> None:

    logger.info(
        "AAS live-sync watch loop started (interval=%.0fs)", poll_interval_seconds
    )
    while True:
        await asyncio.sleep(poll_interval_seconds)
        try:
            now = datetime.now(timezone.utc)
            stale_cutoff = poll_interval_seconds * 5
            for device in registry.all_devices():
                age = (now - device.last_seen).total_seconds()
                if age > stale_cutoff:
                    await retire_device_in_fuseki(
                        device.device_id, fuseki_data_endpoint
                    )
        except Exception as exc:
            logger.error("AAS watch loop error: %s", exc, exc_info=True)
