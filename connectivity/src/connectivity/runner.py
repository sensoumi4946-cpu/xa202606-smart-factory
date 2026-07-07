import asyncio
import argparse
from typing import Optional

from connectivity.adapters.base import BaseAdapter


ALL_ADAPTERS = ("mqtt", "modbus", "rest", "opcua")


def build_adapter(name: str) -> BaseAdapter:
    if name == "mqtt":
        from connectivity.adapters.mqtt_adapter import MQTTAdapter

        return MQTTAdapter()
    if name == "modbus":
        from connectivity.adapters.modbus_adapter import ModbusAdapter

        return ModbusAdapter()
    if name == "rest":
        from connectivity.adapters.rest_adapter import RESTAdapter

        return RESTAdapter()
    if name == "opcua":
        from connectivity.adapters.opcua_adapter import OPCUAAdapter

        return OPCUAAdapter()
    raise ValueError(f"unsupported adapter: {name}")


def parse_args(argv: Optional[list[str]] = None):
    parser = argparse.ArgumentParser(description="Run a connectivity adapter")
    parser.add_argument(
        "--adapter",
        choices=["mqtt", "modbus", "rest", "opcua", "all"],
        default="mqtt",
        help="Adapter to run",
    )
    return parser.parse_args(argv)


async def _run_adapter(name: str) -> None:
    adapter = build_adapter(name)
    try:
        await adapter.start()
    except KeyboardInterrupt:
        pass
    finally:
        await adapter.stop()


async def main(argv: Optional[list[str]] = None):
    args = parse_args(argv)
    if args.adapter == "all":
        tasks = [asyncio.create_task(_run_adapter(name)) for name in ALL_ADAPTERS]
        await asyncio.gather(*tasks)
    else:
        await _run_adapter(args.adapter)


if __name__ == "__main__":
    asyncio.run(main())
