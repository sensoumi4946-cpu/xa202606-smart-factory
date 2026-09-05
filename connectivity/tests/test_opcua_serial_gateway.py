import json

import pytest

from connectivity.gateways.opcua_serial import parse_distance


def test_parse_distance():
    assert parse_distance(json.dumps({"distance": 13.6}).encode()) == 13.6


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_reject_invalid_distance(value):
    with pytest.raises(ValueError):
        parse_distance(json.dumps({"distance": value}).encode())
