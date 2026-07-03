import sys
import asyncio
from types import ModuleType

from analytics.mock.modbus_server import (
    create_context,
    get_device,
    next_registers,
    set_registers,
    start_server,
)


def test_next_registers_shape():
    registers = next_registers()
    assert len(registers) == 3
    assert all(isinstance(value, int) for value in registers)


class FakeBlock:
    def __init__(self, address, values):
        self.address = address
        self.values = values


class FakeDevice:
    def __init__(self):
        self.calls = []

    def setValues(self, table, address, values):
        self.calls.append((table, address, values))


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
    assert context.devices.hr.address == 1


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
    assert context.slaves.hr.address == 1


def test_set_registers_uses_pymodbus_4_devices():
    device = FakeDevice()

    class FakeContext:
        _devices = {0: device}

    set_registers(FakeContext(), [3, 12, 0])
    assert device.calls == [(3, 0, [3, 12, 0])]


def test_set_registers_prefers_devices_when_indexing_fails():
    device = FakeDevice()

    class FakeContext:
        _devices = {0: device}

        def __getitem__(self, key):
            raise TypeError("context index disabled")

    assert get_device(FakeContext()) is device
    set_registers(FakeContext(), [3, 12, 0])
    assert device.calls == [(3, 0, [3, 12, 0])]


def test_set_registers_falls_back_to_public_devices():
    device = FakeDevice()

    class FakeContext:
        devices = {0: device}

    set_registers(FakeContext(), [3, 12, 0])
    assert device.calls == [(3, 0, [3, 12, 0])]


def test_set_registers_falls_back_to_pymodbus_3_index():
    device = FakeDevice()

    class FakeContext:
        def __getitem__(self, key):
            assert key == 0
            return device

    set_registers(FakeContext(), [3, 12, 0])
    assert device.calls == [(3, 0, [3, 12, 0])]


def test_start_server_uses_pymodbus_4_server(monkeypatch):
    server_module = ModuleType("pymodbus.server")
    calls = []

    class FakeServer:
        def __init__(self, context, address):
            calls.append((context, address))

        async def serve_forever(self):
            calls.append("served")

    server_module.ModbusTcpServer = FakeServer
    monkeypatch.setitem(sys.modules, "pymodbus.server", server_module)

    context = object()
    asyncio.run(start_server(context))
    assert calls == [(context, ("0.0.0.0", 1502)), "served"]


def test_start_server_falls_back_to_pymodbus_3_function(monkeypatch):
    server_module = ModuleType("pymodbus.server")
    calls = []

    async def fake_start(context, address):
        calls.append((context, address))

    server_module.StartAsyncTcpServer = fake_start
    monkeypatch.setitem(sys.modules, "pymodbus.server", server_module)

    context = object()
    asyncio.run(start_server(context))
    assert calls == [(context, ("0.0.0.0", 1502))]
