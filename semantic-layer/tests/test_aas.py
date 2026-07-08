# AAS descriptor validation tests.
# Loads the five subsystem descriptors and the index from semantic-layer/aas/
# (path relative to this test file, working-directory independent) and checks
# structure, enum consistency with the shared contracts, and semantic URI
# alignment with the ontology. Descriptor-ready only — no BaSyx runtime.
import json
from pathlib import Path

from smart_factory_contracts.messages import Protocol, Subsystem

AAS_DIR = Path(__file__).resolve().parent.parent / "aas"

SUBSYSTEM_FILES = {
    "temp_humidity": "aas_temp_humidity.json",
    "lighting": "aas_lighting.json",
    "gas": "aas_gas.json",
    "agv": "aas_agv.json",
    "counting": "aas_counting.json",
}


def _load(name: str) -> dict:
    with open(AAS_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def test_all_five_subsystems_present_in_index():
    index = _load("aas_index.json")
    subsystems = {s["subsystem"] for s in index["shells"]}
    assert subsystems == {s.value for s in Subsystem}
    files = {s["file"] for s in index["shells"]}
    assert files == set(SUBSYSTEM_FILES.values())


def test_each_aas_has_subsystem_and_protocol():
    valid_subsystems = {s.value for s in Subsystem}
    valid_protocols = {p.value for p in Protocol}
    for subsystem, filename in SUBSYSTEM_FILES.items():
        aas = _load(filename)
        submodel = aas["submodels"][0]
        assert submodel["subsystem"] == subsystem
        assert submodel["subsystem"] in valid_subsystems
        assert submodel["protocol"] in valid_protocols


def test_observed_properties_semantic_uris():
    prefix = "http://example.org/smart-factory#measures"
    for filename in SUBSYSTEM_FILES.values():
        aas = _load(filename)
        props = aas["submodels"][0]["observedProperties"]
        assert len(props) >= 1
        for prop in props:
            assert prop["semanticUri"].startswith(prefix)
            assert len(prop["type"]) > 0
            assert len(prop["unit"]) > 0


def test_temp_humidity_has_high_temp_demo_role():
    aas = _load("aas_temp_humidity.json")
    assert "高温告警联动" in aas["submodels"][0]["demoRole"]


def test_control_capabilities_unsupported():
    for filename in SUBSYSTEM_FILES.values():
        aas = _load(filename)
        caps = aas["submodels"][0]["controlCapabilities"]
        assert caps["supported"] is False
