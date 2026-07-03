import pytest

from connectivity.runner import parse_args


def test_runner_default_adapter():
    args = parse_args([])
    assert args.adapter == "mqtt"


def test_runner_modbus_adapter():
    args = parse_args(["--adapter", "modbus"])
    assert args.adapter == "modbus"


def test_runner_invalid_adapter():
    with pytest.raises(SystemExit):
        parse_args(["--adapter", "invalid"])
