import pytest

from connectivity.runner import parse_args


def test_runner_default_adapter():
    args = parse_args([])
    assert args.adapter == "mqtt"


def test_runner_opcua_adapter():
    args = parse_args(["--adapter", "opcua"])
    assert args.adapter == "opcua"


def test_runner_invalid_adapter():
    with pytest.raises(SystemExit):
        parse_args(["--adapter", "invalid"])
