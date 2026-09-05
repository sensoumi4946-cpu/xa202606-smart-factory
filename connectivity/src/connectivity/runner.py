import asyncio
import argparse
import contextlib
import logging
import signal
from typing import Optional

from connectivity.adapters.base import BaseAdapter


ALL_ADAPTERS = ("mqtt", "modbus", "rest", "opcua")
logger = logging.getLogger(__name__)


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


async def _stop_adapters(adapters: list[BaseAdapter]) -> None:
    await asyncio.gather(*(adapter.stop() for adapter in adapters))


async def supervise(
    names: tuple[str, ...],
    reload_event: asyncio.Event,
    stop_event: asyncio.Event,
) -> None:
    """Keep adapters alive and rebuild binding-derived plans on SIGHUP."""
    while not stop_event.is_set():
        adapters = [build_adapter(name) for name in names]
        adapter_task = asyncio.gather(*(adapter.start() for adapter in adapters))
        reload_task = asyncio.create_task(reload_event.wait())
        stop_task = asyncio.create_task(stop_event.wait())
        try:
            done, _ = await asyncio.wait(
                {adapter_task, reload_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if adapter_task in done:
                await adapter_task
                return
            await _stop_adapters(adapters)
            await adapter_task
            if stop_task in done:
                return
            reload_event.clear()
            logger.info("adapter bindings reloaded for %s", ",".join(names))
        finally:
            for task in (reload_task, stop_task):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task


def _register_signal_handlers(
    reload_event: asyncio.Event, stop_event: asyncio.Event
) -> None:
    loop = asyncio.get_running_loop()
    for sig, event in (
        (getattr(signal, "SIGHUP", None), reload_event),
        (signal.SIGTERM, stop_event),
        (signal.SIGINT, stop_event),
    ):
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, event.set)
        except (NotImplementedError, RuntimeError):
            # Windows and embedded event loops may not expose POSIX signals.
            pass


async def _run_adapter(name: str) -> None:
    reload_event = asyncio.Event()
    stop_event = asyncio.Event()
    _register_signal_handlers(reload_event, stop_event)
    try:
        await supervise((name,), reload_event, stop_event)
    except KeyboardInterrupt:
        stop_event.set()


async def main(argv: Optional[list[str]] = None):
    args = parse_args(argv)
    logging.basicConfig(level="INFO")
    if args.adapter == "all":
        reload_event = asyncio.Event()
        stop_event = asyncio.Event()
        _register_signal_handlers(reload_event, stop_event)
        await supervise(ALL_ADAPTERS, reload_event, stop_event)
    else:
        await _run_adapter(args.adapter)


if __name__ == "__main__":
    asyncio.run(main())
