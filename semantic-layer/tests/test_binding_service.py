import asyncio
import signal
from pathlib import Path

from semantic_layer.binding_service import BindingService, run

REPO_ROOT = Path(__file__).resolve().parents[2]


def _bindings_path() -> Path:
    return REPO_ROOT / "bindings.ttl"


def test_binding_service_status():
    service = BindingService(_bindings_path())
    status = service.handle({"op": "status"})
    assert status["ok"] is True
    assert status["bindings"] >= 1
    assert status["devices"]


def test_binding_service_starts_when_socket_does_not_exist(
    tmp_path, monkeypatch
):
    socket_path = tmp_path / "fresh" / "bindings.sock"

    async def exercise():
        callbacks = {}
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(
            loop, "add_signal_handler", lambda sig, callback: callbacks.setdefault(sig, callback)
        )

        class FakeServer:
            async def __aenter__(self):
                loop.call_soon(callbacks[signal.SIGTERM])
                return self

            async def __aexit__(self, *_):
                return False

        async def fake_start_unix_server(_, path):
            socket_file = tmp_path / "fresh" / "bindings.sock"
            assert path == str(socket_file)
            socket_file.touch()
            return FakeServer()

        monkeypatch.setattr(asyncio, "start_unix_server", fake_start_unix_server)
        assert await run(str(socket_path), _bindings_path()) == 0

    asyncio.run(exercise())
    assert not socket_path.exists()
