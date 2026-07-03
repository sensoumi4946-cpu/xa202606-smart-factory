import asyncio
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


async def run() -> None:
    from pymodbus.datastore import (
        ModbusSequentialDataBlock,
        ModbusServerContext,
        ModbusSlaveContext,
    )
    from pymodbus.server import StartAsyncTcpServer

    store = ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, [0] * 10))
    context = ModbusServerContext(slaves=store, single=True)
    asyncio.create_task(update_loop(context))
    await StartAsyncTcpServer(context=context, address=("0.0.0.0", MODBUS_SIM_PORT))


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
