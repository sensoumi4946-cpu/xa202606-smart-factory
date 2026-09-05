# Tests for the semantic runtime: ingest → Fuseki trigger and the
# GET /api/v1/semantic read views.

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from smart_factory_contracts.messages import (
    Measurement,
    MeasurementType,
    Protocol,
    Subsystem,
    UnifiedMessage,
    Unit,
)

from backend.api import ingest as ingest_mod
from backend.api import semantic as semantic_mod
from backend.main import app
from backend.store import init_db

SF = "http://example.org/smart-factory#"


@pytest.fixture(autouse=True)
def _init_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("backend.store.DATABASE_PATH", str(db_path))
    monkeypatch.setattr("backend.config.DATABASE_PATH", str(db_path))
    init_db()


def _msg():
    return UnifiedMessage(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        measurements=[
            Measurement(
                type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS
            ),
        ],
    )


# Fake async httpx client for the SPARQL query path


class _FakeResp:
    def __init__(self, payload, raise_exc=None):
        self._payload = payload
        self._raise = raise_exc
        self.status_code = 200

    def raise_for_status(self):
        if self._raise:
            raise self._raise

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload=None, post_exc=None, **kwargs):
        self._payload = payload
        self._post_exc = post_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *args, **kwargs):
        if self._post_exc:
            raise self._post_exc
        return _FakeResp(self._payload)


def _bind(var_uri):
    return {"type": "uri", "value": var_uri}


_SPARQL_JSON = {
    "head": {"vars": ["sensor", "subsystem", "protocol", "prop"]},
    "results": {
        "bindings": [
            {
                "sensor": _bind(f"{SF}sensor_dht22_01"),
                "subsystem": _bind(f"{SF}TempHumiditySubsystem"),
                "protocol": {"type": "literal", "value": "mqtt"},
                "prop": _bind(f"{SF}measuresTemperature"),
            },
            {
                "sensor": _bind(f"{SF}sensor_dht22_01"),
                "subsystem": _bind(f"{SF}TempHumiditySubsystem"),
                "protocol": {"type": "literal", "value": "mqtt"},
                "prop": _bind(f"{SF}measuresHumidity"),
            },
            {
                "sensor": _bind(f"{SF}sensor_mq2_01"),
                "subsystem": _bind(f"{SF}GasMonitoringSubsystem"),
                "protocol": {"type": "literal", "value": "modbus"},
                "prop": _bind(f"{SF}measuresCO"),
            },
        ]
    },
}


@pytest.mark.asyncio
async def test_ingest_triggers_semantic_write(monkeypatch):
    calls = []

    async def fake_write(msg, endpoint):
        calls.append((msg.device_id, endpoint))
        return True

    monkeypatch.setattr("backend.config.SEMANTIC_WRITE_ENABLED", True)
    monkeypatch.setattr(ingest_mod, "write_to_fuseki", fake_write)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/ingest/api/v1/data", json=_msg().model_dump(mode="json")
        )
    assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == "sensor_dht22_01"


@pytest.mark.asyncio
async def test_failed_semantic_write_logs_warning(monkeypatch, caplog):
    async def fake_write(msg, endpoint):
        return False

    monkeypatch.setattr("backend.config.SEMANTIC_WRITE_ENABLED", True)
    monkeypatch.setattr(ingest_mod, "write_to_fuseki", fake_write)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/ingest/api/v1/data", json=_msg().model_dump(mode="json")
        )
    assert resp.status_code == 200
    assert resp.json()["kg_write"] == "queued"
    assert "Fuseki write returned false" in caplog.text


@pytest.mark.asyncio
async def test_semantic_view_sensor_observations(monkeypatch):
    monkeypatch.setattr(
        semantic_mod.httpx,
        "AsyncClient",
        lambda **kw: _FakeClient(payload=_SPARQL_JSON, **kw),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/semantic?view=sensor-observations")
    assert resp.status_code == 200
    data = resp.json()
    assert data["view"] == "sensor-observations"
    by_id = {r["sensor"]: r for r in data["results"]}
    assert set(by_id) == {"sensor_dht22_01", "sensor_mq2_01"}
    assert by_id["sensor_dht22_01"]["subsystem"] == "temp_humidity"
    assert set(by_id["sensor_dht22_01"]["observes"]) == {"temperature", "humidity"}
    assert by_id["sensor_dht22_01"]["protocol"] == "mqtt"
    assert by_id["sensor_mq2_01"]["subsystem"] == "gas"
    assert "co" in by_id["sensor_mq2_01"]["observes"]


@pytest.mark.asyncio
async def test_semantic_unavailable_returns_degraded_view(monkeypatch):
    monkeypatch.setattr(
        semantic_mod.httpx,
        "AsyncClient",
        lambda **kw: _FakeClient(post_exc=httpx.ConnectError("refused"), **kw),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/semantic?view=sensor-observations")
    assert resp.status_code == 200
    assert resp.json()["degraded"] is True
    assert resp.json()["results"] == []


@pytest.mark.asyncio
async def test_semantic_unknown_view_returns_400():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        bad = await client.get("/api/v1/semantic?view=bogus")
        missing = await client.get("/api/v1/semantic")
    assert bad.status_code == 400
    assert bad.json()["detail"].startswith("Unknown view")
    assert missing.status_code == 400
