import asyncio
import importlib
import os
import random

MODBUS_SIM_PORT = int(os.getenv("MODBUS_SIM_PORT", "1502"))
MODBUS_UPDATE_INTERVAL = float(os.getenv("MODBUS_UPDATE_INTERVAL", "2"))


def next_registers() -> list[int]:
    return [random.randint(0, 10), random.randint(0, 50), random.randint(0, 5)]


async def update_loop(context, interval: float = MODBUS_UPDATE_INTERVAL) -> None:
    while True:
        context[0].setValues(3, 0, next_registers())
        await asyncio.sleep(interval)


def create_context():
    datastore = importlib.import_module("pymodbus.datastore")
    block = datastore.ModbusSequentialDataBlock(0, [0] * 10)
    device_cls = getattr(datastore, "ModbusDeviceContext", None) or getattr(
        datastore, "ModbusSlaveContext"
    )
    store = device_cls(hr=block)
    try:
        return datastore.ModbusServerContext(devices=store, single=True)
    except TypeError:
        return datastore.ModbusServerContext(slaves=store, single=True)


async def run() -> None:
    from pymodbus.server import StartAsyncTcpServer

    context = create_context()
    asyncio.create_task(update_loop(context))
    await StartAsyncTcpServer(context=context, address=("0.0.0.0", MODBUS_SIM_PORT))


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
