import asyncio

import pytest

from connectivity.adapters import modbus_adapter
from connectivity.adapters.modbus_adapter import ModbusAdapter
from connectivity.generated_adapters import GeneratedAdapterSet
from semantic_layer.protocol_binding import BindingRegistry

GAS_BINDINGS = """
@prefix sf: <http://example.org/smart-factory#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

sf:smoke a sf:ProtocolBinding ; sf:bindsProperty sf:measuresSmoke ;
  sf:transportProtocol "modbus" ; sf:deviceId "gas-1" ;
  sf:belongsToSubsystem sf:GasSubsystem ; sf:hasUnit "ppm" ;
  sf:registerAddress 40001 ; sf:registerBase 40001 ; sf:functionCode 3 ;
  sf:registerType "uint16" ; sf:scaleFactor "0.1"^^xsd:double ; sf:slaveId 1 .
sf:co a sf:ProtocolBinding ; sf:bindsProperty sf:measuresCo ;
  sf:transportProtocol "modbus" ; sf:deviceId "gas-1" ;
  sf:belongsToSubsystem sf:GasSubsystem ; sf:hasUnit "ppm" ;
  sf:registerAddress 40002 ; sf:registerBase 40001 ; sf:functionCode 3 ;
  sf:registerType "uint16" ; sf:scaleFactor "0.1"^^xsd:double ; sf:slaveId 1 .
sf:gas a sf:ProtocolBinding ; sf:bindsProperty sf:measuresCombustibleGas ;
  sf:transportProtocol "modbus" ; sf:deviceId "gas-1" ;
  sf:belongsToSubsystem sf:GasSubsystem ; sf:hasUnit "ppm" ;
  sf:registerAddress 40003 ; sf:registerBase 40001 ; sf:functionCode 3 ;
  sf:registerType "uint16" ; sf:scaleFactor "0.1"^^xsd:double ; sf:slaveId 1 .
"""


@pytest.fixture
def adapter():
    registry = BindingRegistry()
    result = registry.load_turtle(GAS_BINDINGS)
    assert result.accepted, result.violations
    return ModbusAdapter(GeneratedAdapterSet(registry))


def by_type(message, measurement_type: str):
    return {m.type.value: m for m in message.measurements}[measurement_type]


def test_read_plan_is_ontology_driven(adapter):
    assert adapter.bindings.modbus_read_plans()[0]["address"] == 0
    assert adapter.bindings.modbus_read_plans()[0]["count"] == 3


def test_modbus_connection_refused(adapter):
    class FakeClient:
        async def connect(self):
            return False

    assert asyncio.run(adapter._connect(FakeClient())) is False


def test_modbus_forward_to_backend(adapter, monkeypatch):
    class FakeResult:
        registers = [30, 120, 0]

        def isError(self):
            return False

    class FakeClient:
        async def read_holding_registers(self, address, count, device_id):
            assert (address, count, device_id) == (0, 3, 1)
            return FakeResult()

    captured = []

    async def fake_forward(message):
        captured.append(message)
        return True

    monkeypatch.setattr(modbus_adapter, "forward_to_backend", fake_forward)
    message = asyncio.run(adapter.poll_once(FakeClient()))
    assert message is not None
    assert by_type(message, "smoke").value == pytest.approx(3.0)
    assert by_type(message, "co").value == pytest.approx(12.0)
    assert by_type(message, "combustible_gas").value == pytest.approx(0.0)
    assert captured == [message]
