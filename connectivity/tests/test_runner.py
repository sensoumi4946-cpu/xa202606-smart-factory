import asyncio

import pytest

from connectivity import runner
from connectivity.runner import parse_args


def test_runner_default_adapter():
    args = parse_args([])
    assert args.adapter == "mqtt"


def test_runner_modbus_adapter():
    args = parse_args(["--adapter", "modbus"])
    assert args.adapter == "modbus"


def test_runner_rest_adapter():
    args = parse_args(["--adapter", "rest"])
    assert args.adapter == "rest"


def test_runner_opcua_adapter():
    args = parse_args(["--adapter", "opcua"])
    assert args.adapter == "opcua"


def test_runner_invalid_adapter():
    with pytest.raises(SystemExit):
        parse_args(["--adapter", "invalid"])


def test_runner_all_adapter():
    args = parse_args(["--adapter", "all"])
    assert args.adapter == "all"


def test_sighup_rebuilds_adapter_binding_plan(monkeypatch):
    created = []

    class FakeAdapter:
        def __init__(self):
            self.running = False
            self.started = asyncio.Event()
            created.append(self)

        async def start(self):
            self.running = True
            self.started.set()
            while self.running:
                await asyncio.sleep(0)

        async def stop(self):
            self.running = False

    monkeypatch.setattr(runner, "build_adapter", lambda _: FakeAdapter())

    async def exercise():
        reload_event = asyncio.Event()
        stop_event = asyncio.Event()
        task = asyncio.create_task(
            runner.supervise(("mqtt",), reload_event, stop_event)
        )
        while len(created) < 1 or not created[0].started.is_set():
            await asyncio.sleep(0)
        reload_event.set()
        while len(created) < 2 or not created[1].started.is_set():
            await asyncio.sleep(0)
        stop_event.set()
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(exercise())
    assert len(created) == 2
