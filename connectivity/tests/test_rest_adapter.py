import asyncio

import httpx

from connectivity.adapters import rest_adapter
from connectivity.adapters.rest_adapter import create_app, parse_payload


def by_type(msg, measurement_type: str):
    return {m.type.value: m for m in msg.measurements}[measurement_type]


def post_json(payload):
    async def send():
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.post("/adapter/rest/ingest", json=payload)

    return asyncio.run(send())


def test_rest_lighting_payload():
    msg = parse_payload(
        {"device": "sensor_pir_01", "metrics": {"occupancy": "active", "light": "on"}}
    )
    assert msg.schema_version == "v1"
    assert msg.device_id == "sensor_pir_01"
    assert msg.subsystem.value == "lighting"
    assert msg.protocol.value == "rest"
    assert by_type(msg, "occupancy").value == 1.0
    assert by_type(msg, "light_state").value == 1.0
    assert msg.raw_payload == {
        "device": "sensor_pir_01",
        "metrics": {"occupancy": "active", "light": "on"},
    }


def test_rest_counting_payload():
    msg = parse_payload({"d": "sensor_ir_01", "v": 42})
    assert msg.schema_version == "v1"
    assert msg.device_id == "sensor_ir_01"
    assert msg.subsystem.value == "counting"
    assert msg.protocol.value == "rest"
    assert by_type(msg, "count").value == 42.0
    assert msg.raw_payload == {"d": "sensor_ir_01", "v": 42}


def test_rest_invalid_payload_400():
    resp = post_json({"unexpected": True})
    assert resp.status_code == 400
    assert resp.json() == {"detail": "unknown payload format"}


def test_rest_ambiguous_payload_400():
    resp = post_json(
        {"device": "sensor_pir_01", "metrics": {}, "d": "sensor_ir_01", "v": 1}
    )
    assert resp.status_code == 400
    assert resp.json() == {"detail": "ambiguous payload"}


def test_rest_forward_to_backend(monkeypatch):
    captured = []

    async def fake_forward(msg):
        captured.append(msg)
        return True

    monkeypatch.setattr(rest_adapter, "forward_to_backend", fake_forward)
    resp = post_json(
        {
            "device": "sensor_pir_01",
            "metrics": {"occupancy": "inactive", "light": "off"},
        }
    )
    assert resp.status_code == 202
    assert resp.json() == {"status": "accepted"}
    assert captured[0].device_id == "sensor_pir_01"
    assert captured[0].protocol.value == "rest"
    assert by_type(captured[0], "occupancy").value == 0.0
    assert by_type(captured[0], "light_state").value == 0.0


def test_rest_forward_failure_502(monkeypatch):
    async def fake_forward(msg):
        return False

    monkeypatch.setattr(rest_adapter, "forward_to_backend", fake_forward)
    resp = post_json({"d": "sensor_ir_01", "v": 42})
    assert resp.status_code == 502
    assert resp.json() == {"detail": "backend forward failed"}
