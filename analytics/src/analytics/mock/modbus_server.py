import asyncio
import inspect
import importlib
import os
import random

MODBUS_SIM_PORT = int(os.getenv("MODBUS_SIM_PORT", "1502"))
MODBUS_UPDATE_INTERVAL = float(os.getenv("MODBUS_UPDATE_INTERVAL", "2"))


def next_registers() -> list[int]:
    return [random.randint(0, 10), random.randint(0, 50), random.randint(0, 5)]


async def update_loop(context, interval: float = MODBUS_UPDATE_INTERVAL) -> None:
    while True:
        update_once(context)
        await asyncio.sleep(interval)


def update_once(context) -> None:
    set_registers(context, next_registers())


def set_registers(context, registers: list[int]) -> None:
    device = get_device(context)
    device.setValues(3, 0, registers)


def get_device(context):
    try:
        devices = context.devices
        try:
            return devices[0]
        except (KeyError, TypeError, IndexError):
            return devices
    except AttributeError:
        return context[0]


def create_context():
    datastore = importlib.import_module("pymodbus.datastore")
    block = datastore.ModbusSequentialDataBlock(1, [0] * 10)
    device_cls = getattr(datastore, "ModbusDeviceContext", None) or getattr(
        datastore, "ModbusSlaveContext"
    )
    store = device_cls(hr=block)
    try:
        return datastore.ModbusServerContext(devices=store, single=True)
    except TypeError:
        return datastore.ModbusServerContext(slaves=store, single=True)


async def start_server(context) -> None:
    server_module = importlib.import_module("pymodbus.server")
    address = ("0.0.0.0", MODBUS_SIM_PORT)
    if hasattr(server_module, "ModbusTcpServer"):
        server = server_module.ModbusTcpServer(context, address=address)
        result = server.serve_forever()
        if inspect.isawaitable(result):
            await result
        return
    await server_module.StartAsyncTcpServer(context=context, address=address)


async def run() -> None:
    context = create_context()
    asyncio.create_task(update_loop(context))
    await start_server(context)


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
