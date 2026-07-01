import pytest
from httpx import ASGITransport, AsyncClient
from smart_factory_contracts.messages import Measurement, MeasurementType, Protocol, Subsystem, UnifiedMessage, Unit

from connectivity.router import forward_to_backend


async def _make_backend_app():
    from backend.main import app
    from backend.store import init_db
    return app


@pytest.mark.asyncio
async def test_forward_to_backend_success(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("backend.store.DATABASE_PATH", str(db_path))
    monkeypatch.setattr("backend.config.DATABASE_PATH", str(db_path))
    from backend.store import init_db
    init_db()

    app = await _make_backend_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async def fake_post(url, json):
            return await client.post("/api/v1/data", json=json)

        msg = UnifiedMessage(
            device_id="sensor_dht22_01",
            subsystem=Subsystem.TEMP_HUMIDITY,
            protocol=Protocol.MQTT,
            measurements=[
                Measurement(type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS),
            ],
        )
        import asyncio
        result = await forward_to_backend(msg)
        assert result is True


@pytest.mark.asyncio
async def test_forward_to_backend_failure():
    old_url = None
    import connectivity.router as router_mod
    if hasattr(router_mod, "BACKEND_URL"):
        old_url = router_mod.BACKEND_URL

    try:
        import connectivity.models as models_mod
        models_mod.BACKEND_URL = "http://localhost:19999"

        msg = UnifiedMessage(
            device_id="sensor_dht22_01",
            subsystem=Subsystem.TEMP_HUMIDITY,
            protocol=Protocol.MQTT,
            measurements=[
                Measurement(type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS),
            ],
        )
        result = await forward_to_backend(msg)
        assert result is False
    finally:
        if old_url is not None:
            import connectivity.models as models_mod
            models_mod.BACKEND_URL = old_url
