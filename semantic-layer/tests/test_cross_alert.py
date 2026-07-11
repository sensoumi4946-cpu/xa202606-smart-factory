import pytest
import httpx
from semantic_layer.cross_alert import check_fire_risk, TEMP_THRESHOLD, GAS_THRESHOLD


class _MockResponse:
    def __init__(self, bindings: list):
        self._body = {"results": {"bindings": bindings}}
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


class _MockClient:
    def __init__(self, bindings_or_exc):
        self._result = bindings_or_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        if isinstance(self._result, Exception):
            raise self._result
        return _MockResponse(self._result)


def _patch(monkeypatch, result):
    import semantic_layer.cross_alert as mod
    monkeypatch.setattr(mod.httpx, "AsyncClient", lambda **kw: _MockClient(result))


def _row(temp_sensor, temp_val, gas_sensor, gas_val):
    def _uri(name):
        return {"type": "uri", "value": f"http://example.org/smart-factory#{name}"}
    def _lit(val):
        return {"type": "literal", "value": str(val)}
    return {
        "tempSensor": _uri(temp_sensor),
        "tempVal":    _lit(temp_val),
        "gasSensor":  _uri(gas_sensor),
        "gasVal":     _lit(gas_val),
    }


@pytest.mark.asyncio
async def test_no_bindings_returns_none(monkeypatch):
    _patch(monkeypatch, [])
    result = await check_fire_risk("http://fuseki:3030/factory/query")
    assert result is None


@pytest.mark.asyncio
async def test_risk_detected_returns_dict(monkeypatch):
    _patch(monkeypatch, [_row("sensor_dht22_01", 38.5, "sensor_mq2_01", 42.0)])
    result = await check_fire_risk("http://fuseki:3030/factory/query")
    assert result is not None
    assert result["risk"] == "fire"
    assert result["temp_sensor"] == "sensor_dht22_01"
    assert result["gas_sensor"]  == "sensor_mq2_01"
    assert result["temp_val"]    == 38.5
    assert result["gas_val"]     == 42.0


@pytest.mark.asyncio
async def test_thresholds_included_in_result(monkeypatch):
    _patch(monkeypatch, [_row("sensor_dht22_01", 38.5, "sensor_mq2_01", 42.0)])
    result = await check_fire_risk("http://fuseki:3030/factory/query")
    assert result["thresholds"]["temperature"] == TEMP_THRESHOLD
    assert result["thresholds"]["gas"]         == GAS_THRESHOLD


@pytest.mark.asyncio
async def test_fuseki_unreachable_returns_none(monkeypatch):
    _patch(monkeypatch, httpx.ConnectError("refused"))
    result = await check_fire_risk("http://fuseki:3030/factory/query")
    assert result is None


@pytest.mark.asyncio
async def test_fuseki_timeout_returns_none(monkeypatch):
    _patch(monkeypatch, httpx.TimeoutException("timed out"))
    result = await check_fire_risk("http://fuseki:3030/factory/query")
    assert result is None


@pytest.mark.asyncio
async def test_local_name_extracted_from_uri(monkeypatch):
    _patch(monkeypatch, [_row("sensor_dht22_01", 37.0, "sensor_mq2_01", 36.5)])
    result = await check_fire_risk("http://fuseki:3030/factory/query")
    assert "#" not in result["temp_sensor"]
    assert "#" not in result["gas_sensor"]
