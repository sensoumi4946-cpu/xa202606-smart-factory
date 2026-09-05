from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from analytics.thresholds import resolver
from backend import config
from backend.api import innovation_api
from backend.main import app
from semantic_layer.meta_model import registry as meta_registry

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _restore_runtime_configuration():
    old_bindings = config.BINDINGS_TTL
    old_thresholds = config.THRESHOLDS_TTL
    yield
    config.BINDINGS_TTL = old_bindings
    config.THRESHOLDS_TTL = old_thresholds
    innovation_api.load_bindings(old_bindings)
    innovation_api.load_thresholds(old_thresholds)


@pytest.mark.asyncio
async def test_reload_endpoint_loads_bindings_and_thresholds():
    config.BINDINGS_TTL = str(REPO_ROOT / "bindings.ttl")
    config.THRESHOLDS_TTL = str(REPO_ROOT / "thresholds.ttl")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/innovation/reload")
    assert response.status_code == 200
    body = response.json()
    assert body["bindings"] == 17
    assert body["thresholds"]["properties"] == [
        "co",
        "combustible_gas",
        "count",
        "distance",
        "humidity",
        "light_state",
        "occupancy",
        "smoke",
        "temperature",
    ]
    assert resolver.resolve_source("temperature") == "ontology"


def test_invalid_binding_reload_preserves_active_registry(tmp_path):
    config.BINDINGS_TTL = str(REPO_ROOT / "bindings.ttl")
    assert innovation_api.load_bindings() == 17
    active = innovation_api.binding_registry
    invalid = tmp_path / "invalid.ttl"
    invalid.write_text("not turtle", encoding="utf-8")
    assert innovation_api.load_bindings(str(invalid)) == 0
    assert innovation_api.binding_registry is active
    assert len(innovation_api.binding_registry) == 17


def test_threshold_file_loads_all_runtime_values():
    result = innovation_api.load_thresholds(str(REPO_ROOT / "thresholds.ttl"))
    assert result["accepted"] is True
    assert resolver.report()["from_fallback"] == []
    assert meta_registry.thresholds()["distance"] == (30.0, "low")


@pytest.mark.asyncio
async def test_reload_is_all_or_nothing_when_thresholds_are_invalid(tmp_path):
    config.BINDINGS_TTL = str(REPO_ROOT / "bindings.ttl")
    config.THRESHOLDS_TTL = str(REPO_ROOT / "thresholds.ttl")
    assert innovation_api.load_bindings() == 17
    assert innovation_api.load_thresholds()["accepted"] is True
    active_bindings = innovation_api.binding_registry
    active_threshold_version = meta_registry.version

    invalid = tmp_path / "invalid-thresholds.ttl"
    invalid.write_text("not turtle", encoding="utf-8")
    config.THRESHOLDS_TTL = str(invalid)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/innovation/reload")

    assert response.status_code == 500
    assert innovation_api.binding_registry is active_bindings
    assert meta_registry.version == active_threshold_version
