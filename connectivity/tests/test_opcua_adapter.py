import asyncio

from connectivity.adapters import opcua_adapter
from connectivity.adapters.opcua_adapter import (
    OPCUAAdapter,
    SubscriptionHandler,
    make_message_from_node,
)


def test_opcua_node_subscription():
    async def run():
        queue = asyncio.Queue()
        handler = SubscriptionHandler(queue, "ns=2;s=distance", "sensor_hcsr04_01")
        handler.datachange_notification(None, 150.0, None)
        return await asyncio.wait_for(queue.get(), timeout=1.0)

    msg = asyncio.run(run())
    assert msg.schema_version == "v1"
    assert msg.device_id == "sensor_hcsr04_01"
    assert msg.subsystem.value == "agv"
    assert msg.protocol.value == "opcua"
    assert msg.measurements[0].type.value == "distance"
    assert msg.measurements[0].value == 150.0
    assert msg.measurements[0].unit.value == "cm"
    assert msg.raw_payload == {"node_id": "ns=2;s=distance", "value": 150.0}


def test_opcua_message_from_node():
    msg = make_message_from_node("ns=2;s=distance", 120.5)
    assert msg.protocol.value == "opcua"
    assert msg.measurements[0].value == 120.5
    assert msg.measurements[0].unit.value == "cm"


def test_opcua_connection_refused():
    class FakeClient:
        async def connect(self):
            raise OSError("connection refused")

    adapter = OPCUAAdapter()
    assert asyncio.run(adapter._connect(FakeClient())) is False


def test_opcua_forward_to_backend(monkeypatch):
    captured = []

    async def fake_forward(msg):
        captured.append(msg)
        return True

    async def run():
        adapter = OPCUAAdapter()
        adapter._ensure_queue().put_nowait(
            make_message_from_node("ns=2;s=distance", 150.0)
        )
        return await adapter.forward_once(timeout=1.0)

    monkeypatch.setattr(opcua_adapter, "forward_to_backend", fake_forward)
    msg = asyncio.run(run())
    assert msg.device_id == "sensor_hcsr04_01"
    assert captured[0].protocol.value == "opcua"
