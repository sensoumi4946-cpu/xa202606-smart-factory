import asyncio
import argparse
from typing import Optional

from connectivity.adapters.base import BaseAdapter


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
        choices=["mqtt", "modbus", "rest", "opcua"],
        default="mqtt",
        help="Adapter to run",
    )
    return parser.parse_args(argv)


async def main(argv: Optional[list[str]] = None):
    args = parse_args(argv)
    adapter = build_adapter(args.adapter)
    try:
        await adapter.start()
    except KeyboardInterrupt:
        pass
    finally:
        await adapter.stop()


if __name__ == "__main__":
    asyncio.run(main())
