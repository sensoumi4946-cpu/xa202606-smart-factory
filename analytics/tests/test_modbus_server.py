import sys
from types import ModuleType

from analytics.mock.modbus_server import create_context, next_registers


def test_next_registers_shape():
    registers = next_registers()
    assert len(registers) == 3
    assert all(isinstance(value, int) for value in registers)


class FakeBlock:
    def __init__(self, address, values):
        self.address = address
        self.values = values


def test_create_context_uses_pymodbus_4_names(monkeypatch):
    datastore = ModuleType("pymodbus.datastore")

    class FakeDevice:
        def __init__(self, hr):
            self.hr = hr

    class FakeContext:
        def __init__(self, devices, single):
            self.devices = devices
            self.single = single

    datastore.ModbusSequentialDataBlock = FakeBlock
    datastore.ModbusDeviceContext = FakeDevice
    datastore.ModbusServerContext = FakeContext
    monkeypatch.setitem(sys.modules, "pymodbus.datastore", datastore)

    context = create_context()
    assert context.single is True
    assert isinstance(context.devices, FakeDevice)


def test_create_context_falls_back_to_pymodbus_3_names(monkeypatch):
    datastore = ModuleType("pymodbus.datastore")

    class FakeSlave:
        def __init__(self, hr):
            self.hr = hr

    class FakeContext:
        def __init__(self, slaves=None, single=False, devices=None):
            if devices is not None:
                raise TypeError("unexpected devices")
            self.slaves = slaves
            self.single = single

    datastore.ModbusSequentialDataBlock = FakeBlock
    datastore.ModbusSlaveContext = FakeSlave
    datastore.ModbusServerContext = FakeContext
    monkeypatch.setitem(sys.modules, "pymodbus.datastore", datastore)

    context = create_context()
    assert context.single is True
    assert isinstance(context.slaves, FakeSlave)
