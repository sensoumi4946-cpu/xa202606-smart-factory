# Tests for aas_bridge.py — verifies that the five AAS JSON files are
# correctly loaded and converted to RDF triples, and that the helper
# functions used by the REST API work correctly.

import pytest
import httpx
from rdflib import RDF, Graph

from semantic_layer.aas_bridge import (
    SF,
    load_aas_as_rdf,
    get_aas_catalog,
    get_aas_descriptor,
    write_aas_to_fuseki,
)

# load_aas_as_rdf() tests

def test_load_returns_non_empty_graph():
    g = load_aas_as_rdf()
    assert isinstance(g, Graph)
    assert len(g) > 0


def test_five_aas_shells_in_graph():
    g = load_aas_as_rdf()
    shells = list(g.subjects(RDF.type, SF.AssetAdministrationShell))
    assert len(shells) == 5, (
        f"Expected 5 AAS shells but found {len(shells)}: {shells}"
    )


def test_each_shell_linked_to_at_least_one_submodel():
    g = load_aas_as_rdf()
    shells = list(g.subjects(RDF.type, SF.AssetAdministrationShell))
    for shell in shells:
        submodels = list(g.objects(shell, SF.hasSubmodel))
        assert len(submodels) >= 1, f"Shell {shell} has no submodel"


def test_each_submodel_has_subsystem_and_protocol():
    g = load_aas_as_rdf()
    submodels = list(g.subjects(RDF.type, SF.Submodel))
    for sub in submodels:
        subsystems = list(g.objects(sub, SF.subsystem))
        protocols  = list(g.objects(sub, SF.protocol))
        assert len(subsystems) >= 1, f"{sub} missing sf:subsystem"
        assert len(protocols)  >= 1, f"{sub} missing sf:protocol"


def test_gas_shell_has_device():
    g = load_aas_as_rdf()
    gas_shells = [
        s for s in g.subjects(RDF.type, SF.AssetAdministrationShell)
        if "gas" in str(s)
    ]
    assert len(gas_shells) == 1, "Expected exactly one gas AAS shell"
    gas_shell = gas_shells[0]

    submodels = list(g.objects(gas_shell, SF.hasSubmodel))
    all_devices = []
    for sub in submodels:
        all_devices += list(g.objects(sub, SF.hasDevice))

    assert any("sensor_mq2_01" in str(d) for d in all_devices), (
        "sensor_mq2_01 not found in gas shell devices"
    )


def test_all_submodels_have_observable_properties():
    g = load_aas_as_rdf()
    submodels = list(g.subjects(RDF.type, SF.Submodel))
    for sub in submodels:
        props = list(g.objects(sub, SF.hasObservableProperty))
        assert len(props) >= 1, f"{sub} has no hasObservableProperty triples"


def test_observable_property_uris_start_with_smart_factory_prefix():
    g = load_aas_as_rdf()
    submodels = list(g.subjects(RDF.type, SF.Submodel))
    for sub in submodels:
        for prop in g.objects(sub, SF.hasObservableProperty):
            assert str(prop).startswith("http://example.org/smart-factory#"), (
                f"Unexpected property URI: {prop}"
            )


# get_aas_catalog() tests

def test_catalog_returns_five_entries():
    catalog = get_aas_catalog()
    assert len(catalog) == 5


def test_catalog_has_all_subsystem_names():
    catalog = get_aas_catalog()
    subsystems = {entry["subsystem"] for entry in catalog}
    assert subsystems == {"temp_humidity", "lighting", "gas", "agv", "counting"}


def test_catalog_entries_have_required_keys():
    catalog = get_aas_catalog()
    required_keys = {"id", "idShort", "subsystem", "protocol", "globalAssetId", "file"}
    for entry in catalog:
        missing = required_keys - entry.keys()
        assert not missing, f"Catalog entry missing keys: {missing}"


# get_aas_descriptor() tests

def test_descriptor_gas_loads_correctly():
    desc = get_aas_descriptor("gas")
    assert desc is not None
    assert desc["id"] == "urn:smart-factory:aas:gas"
    assert desc["submodels"][0]["subsystem"] == "gas"
    assert desc["submodels"][0]["protocol"] == "modbus"


def test_descriptor_agv_loads_correctly():
    desc = get_aas_descriptor("agv")
    assert desc is not None
    assert "agv" in desc["id"]
    assert desc["submodels"][0]["protocol"] == "opcua"


def test_descriptor_unknown_returns_none():
    assert get_aas_descriptor("unknown_subsystem") is None
    assert get_aas_descriptor("") is None


# write_aas_to_fuseki() tests

class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FakeAsyncClient:
    def __init__(self, status_code_or_exc, **kwargs):
        self._result = status_code_or_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        if isinstance(self._result, Exception):
            raise self._result
        return _FakeResponse(self._result)


def _patch_httpx(monkeypatch, result):
    import semantic_layer.aas_bridge as bridge
    monkeypatch.setattr(bridge.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(result))


@pytest.mark.asyncio
async def test_write_success(monkeypatch):
    _patch_httpx(monkeypatch, 200)
    ok = await write_aas_to_fuseki("http://fuseki:3030/factory/data")
    assert ok is True


@pytest.mark.asyncio
async def test_write_server_error(monkeypatch):
    _patch_httpx(monkeypatch, 500)
    ok = await write_aas_to_fuseki("http://fuseki:3030/factory/data")
    assert ok is False


@pytest.mark.asyncio
async def test_write_connection_refused(monkeypatch):
    _patch_httpx(monkeypatch, httpx.ConnectError("refused"))
    ok = await write_aas_to_fuseki("http://fuseki:3030/factory/data")
    assert ok is False
