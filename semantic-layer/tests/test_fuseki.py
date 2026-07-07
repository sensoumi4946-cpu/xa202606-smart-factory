# Tests for the Fuseki write path (semantic_layer.fuseki).
#
# to_turtle() is verified against real RDF output; write_to_fuseki() is
# exercised with a fake httpx client so no live Fuseki is required. The
# fake covers the three network outcomes: success, connection refused,
# and read timeout.
from datetime import datetime, timezone

import httpx
import pytest
from smart_factory_contracts.messages import (
    Measurement,
    MeasurementType,
    Protocol,
    Subsystem,
    UnifiedMessage,
    Unit,
)

from semantic_layer import fuseki

ENDPOINT = "http://fuseki:3030/factory/data"


def _make_msg(**kwargs):
    defaults = {
        "schema_version": "v1",
        "device_id": "sensor_dht22_01",
        "subsystem": Subsystem.TEMP_HUMIDITY,
        "protocol": Protocol.MQTT,
        "timestamp": datetime(2026, 7, 15, 10, 30, 0, tzinfo=timezone.utc),
        "measurements": [
            Measurement(type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS),
        ],
    }
    defaults.update(kwargs)
    return UnifiedMessage(**defaults)


class _FakeResp:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FakeClient:
    """Minimal async httpx.AsyncClient stand-in.

    post_result is either a status code (returned as a response) or an
    exception instance (raised) to simulate transport failures.
    """

    def __init__(self, post_result, **kwargs):
        self._post_result = post_result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *args, **kwargs):
        if isinstance(self._post_result, Exception):
            raise self._post_result
        return _FakeResp(self._post_result)


def _patch_client(monkeypatch, post_result):
    def factory(*args, **kwargs):
        return _FakeClient(post_result, **kwargs)

    monkeypatch.setattr(fuseki.httpx, "AsyncClient", factory)


def test_to_turtle_contains_observation():
    turtle = fuseki.to_turtle(_make_msg())
    assert "Observation" in turtle
    assert "sensor_dht22_01" in turtle


@pytest.mark.asyncio
async def test_write_success(monkeypatch):
    _patch_client(monkeypatch, 200)
    assert await fuseki.write_to_fuseki(_make_msg(), ENDPOINT) is True


@pytest.mark.asyncio
async def test_write_connection_error(monkeypatch):
    _patch_client(monkeypatch, httpx.ConnectError("refused"))
    assert await fuseki.write_to_fuseki(_make_msg(), ENDPOINT) is False


@pytest.mark.asyncio
async def test_write_timeout(monkeypatch):
    _patch_client(monkeypatch, httpx.ReadTimeout("timed out"))
    assert await fuseki.write_to_fuseki(_make_msg(), ENDPOINT) is False
