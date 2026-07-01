import pytest
from smart_factory_contracts.messages import Measurement, MeasurementType, Protocol, Subsystem, UnifiedMessage, Unit

from connectivity.router import forward_to_backend


@pytest.mark.asyncio
async def test_forward_to_backend_success_starts_backend(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("backend.store.DATABASE_PATH", str(db_path))
    monkeypatch.setattr("backend.config.DATABASE_PATH", str(db_path))
    from backend.store import init_db
    init_db()

    import uvicorn
    import threading
    import time

    port = 19998
    config = uvicorn.Config("backend.main:app", host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(1)

    monkeypatch.setattr("connectivity.models.BACKEND_URL", f"http://127.0.0.1:{port}")

    try:
        msg = UnifiedMessage(
            schema_version="v1",
            device_id="sensor_dht22_01",
            subsystem=Subsystem.TEMP_HUMIDITY,
            protocol=Protocol.MQTT,
            measurements=[
                Measurement(type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS),
            ],
        )
        result = await forward_to_backend(msg)
        assert result is True
    finally:
        server.should_exit = True
        thread.join(timeout=3)


@pytest.mark.asyncio
async def test_forward_to_backend_failure(monkeypatch):
    monkeypatch.setattr("connectivity.models.BACKEND_URL", "http://127.0.0.1:19999")

    msg = UnifiedMessage(
        schema_version="v1",
        device_id="sensor_dht22_01",
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        measurements=[
            Measurement(type=MeasurementType.TEMPERATURE, value=25.5, unit=Unit.CELSIUS),
        ],
    )
    result = await forward_to_backend(msg)
    assert result is False
