import asyncio
import os
import random

OPCUA_SIM_PORT = int(os.getenv("OPCUA_SIM_PORT", "4840"))
OPCUA_UPDATE_INTERVAL = float(os.getenv("OPCUA_UPDATE_INTERVAL", "2"))


def next_distance() -> float:
    return round(random.uniform(10.0, 400.0), 1)


async def update_loop(node, interval: float = OPCUA_UPDATE_INTERVAL) -> None:
    while True:
        await node.set_value(next_distance())
        await asyncio.sleep(interval)


async def run() -> None:
    from asyncua import Server, ua

    server = Server()
    await server.init()
    server.set_endpoint(f"opc.tcp://0.0.0.0:{OPCUA_SIM_PORT}/")
    idx = await server.register_namespace("xa202606")
    agv = await server.nodes.objects.add_object(idx, "AGV")
    node = await agv.add_variable(ua.NodeId("distance", idx), "distance", 150.0)
    await node.set_writable()
    async with server:
        await update_loop(node)


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
