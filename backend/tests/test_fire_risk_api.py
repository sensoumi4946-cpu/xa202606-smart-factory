# Tests for GET /api/v1/semantic/fire-risk
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.mark.asyncio
async def test_fire_risk_reports_false_when_no_condition_detected():
    with patch(
        "backend.api.fire_risk.check_fire_risk",
        new=AsyncMock(return_value=None),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/semantic/fire-risk")
    assert resp.status_code == 200
    assert resp.json() == {"risk_detected": False}


@pytest.mark.asyncio
async def test_fire_risk_reports_true_with_sensor_details_when_detected():
    fake_result = {
        "risk": "fire",
        "temp_sensor": "sensor_dht22_01",
        "temp_val": 78.0,
    }
    with patch(
        "backend.api.fire_risk.check_fire_risk",
        new=AsyncMock(return_value=fake_result),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/semantic/fire-risk")
    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_detected"] is True
    assert body["temp_sensor"] == "sensor_dht22_01"
    assert body["temp_val"] == 78.0


@pytest.mark.asyncio
async def test_fire_risk_endpoint_does_not_crash_when_fuseki_unreachable():
    # check_fire_risk itself swallows httpx errors and returns None —
    # this pins that the endpoint surfaces that as risk_detected: False,
    # not a 500.
    with patch(
        "backend.api.fire_risk.check_fire_risk",
        new=AsyncMock(return_value=None),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/semantic/fire-risk")
    assert resp.status_code == 200
    assert resp.json()["risk_detected"] is False
