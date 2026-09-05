import asyncio

import pytest

from connectivity.adapters import opcua_adapter
from connectivity.adapters.opcua_adapter import (
    OPCUAAdapter,
    SubscriptionHandler,
    make_message_from_node,
)
from connectivity.generated_adapters import GeneratedAdapterSet
from semantic_layer.protocol_binding import BindingRegistry

OPCUA_BINDING = """
@prefix sf: <http://example.org/smart-factory#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
sf:distance a sf:ProtocolBinding ;
  sf:bindsProperty sf:measuresDistance ; sf:transportProtocol "opcua" ;
  sf:deviceId "agv-1" ; sf:belongsToSubsystem sf:AgvSubsystem ;
  sf:hasUnit "cm" ; sf:nodeId "distance" ; sf:namespaceIndex 2 ;
  sf:scaleFactor "1.0"^^xsd:double ; sf:pollIntervalMs 500 .
"""


def adapter_set():
    registry = BindingRegistry()
    result = registry.load_turtle(OPCUA_BINDING)
    assert result.accepted, result.violations
    return GeneratedAdapterSet(registry)


class FakeNodeId:
    def to_string(self):
        return "ns=2;s=distance"


class FakeNode:
    nodeid = FakeNodeId()


def test_opcua_node_subscription():
    async def run():
        queue = asyncio.Queue()
        handler = SubscriptionHandler(queue, adapter_set())
        handler.datachange_notification(FakeNode(), 150.0, None)
        return await asyncio.wait_for(queue.get(), timeout=1.0)

    message = asyncio.run(run())
    assert message.device_id == "agv-1"
    assert message.subsystem.value == "agv"
    assert message.measurements[0].type.value == "distance"
    assert message.measurements[0].unit.value == "cm"


def test_opcua_message_from_node():
    message = make_message_from_node("ns=2;s=distance", 120.5, adapter_set())
    assert message.measurements[0].value == 120.5


def test_opcua_connection_refused():
    class FakeClient:
        async def connect(self):
            raise OSError("connection refused")

    assert asyncio.run(OPCUAAdapter(adapter_set())._connect(FakeClient())) is False


def test_opcua_security_and_credentials(monkeypatch):
    configured = []

    class FakeClient:
        def set_user(self, value):
            configured.append(("user", value))

        def set_password(self, value):
            configured.append(("password", value))

        async def set_security_string(self, value):
            configured.append(("security", value))

        async def load_client_certificate(self, value):
            configured.append(("user_certificate", value))

        async def load_private_key(self, value, password=None):
            configured.append(("user_private_key", str(value), password))

    monkeypatch.setattr(opcua_adapter.connectivity_models, "OPCUA_USERNAME", "edge")
    monkeypatch.setattr(opcua_adapter.connectivity_models, "OPCUA_PASSWORD", "secret")
    monkeypatch.setattr(
        opcua_adapter.connectivity_models,
        "OPCUA_SECURITY_STRING",
        "Basic256Sha256,SignAndEncrypt,client.pem,client-key.pem,server.pem",
    )
    monkeypatch.setattr(
        opcua_adapter.connectivity_models,
        "OPCUA_USER_CERTIFICATE",
        "operator.pem",
    )
    monkeypatch.setattr(
        opcua_adapter.connectivity_models,
        "OPCUA_USER_PRIVATE_KEY",
        "operator-key.pem",
    )
    monkeypatch.setattr(
        opcua_adapter.connectivity_models,
        "OPCUA_USER_PRIVATE_KEY_PASSWORD",
        "key-password",
    )

    asyncio.run(OPCUAAdapter(adapter_set())._configure_client(FakeClient()))

    assert configured == [
        ("user", "edge"),
        ("password", "secret"),
        (
            "security",
            "Basic256Sha256,SignAndEncrypt,client.pem,client-key.pem,server.pem",
        ),
        ("user_certificate", "operator.pem"),
        ("user_private_key", "operator-key.pem", "key-password"),
    ]


def test_opcua_rejects_half_configured_x509_identity(monkeypatch):
    class FakeClient:
        pass

    monkeypatch.setattr(opcua_adapter.connectivity_models, "OPCUA_USERNAME", "")
    monkeypatch.setattr(opcua_adapter.connectivity_models, "OPCUA_PASSWORD", "")
    monkeypatch.setattr(opcua_adapter.connectivity_models, "OPCUA_SECURITY_STRING", "")
    monkeypatch.setattr(
        opcua_adapter.connectivity_models, "OPCUA_USER_CERTIFICATE", "operator.pem"
    )
    monkeypatch.setattr(opcua_adapter.connectivity_models, "OPCUA_USER_PRIVATE_KEY", "")
    with pytest.raises(ValueError):
        asyncio.run(OPCUAAdapter(adapter_set())._configure_client(FakeClient()))


def test_opcua_forward_to_backend(monkeypatch):
    captured = []

    async def fake_forward(message):
        captured.append(message)
        return True

    async def run():
        adapter = OPCUAAdapter(adapter_set())
        adapter._ensure_queue().put_nowait(
            make_message_from_node("ns=2;s=distance", 150.0, adapter.bindings)
        )
        return await adapter.forward_once(timeout=1.0)

    monkeypatch.setattr(opcua_adapter, "forward_to_backend", fake_forward)
    message = asyncio.run(run())
    assert message.device_id == "agv-1"
    assert captured == [message]
