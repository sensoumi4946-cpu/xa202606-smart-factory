# Exports used by other modules:
#   load_aas_as_rdf()          → Graph   (RDFlib graph, no network needed)
#   get_aas_catalog()          → list    (for the REST API endpoint)
#   get_aas_descriptor(name)   → dict    (for the REST API endpoint)
#   write_aas_to_fuseki(url)   → bool    (posts to Fuseki, returns True on 2xx)

import json
from pathlib import Path

import httpx
from rdflib import RDF, Graph, Literal, Namespace, URIRef

# ── Namespace — same prefix the ontology uses ────────────────────────────────
SF = Namespace("http://example.org/smart-factory#")

# ── Path to the AAS JSON files ───────────────────────────────────────────────
# __file__ is .../semantic-layer/src/semantic_layer/aas_bridge.py
# .parent.parent.parent is .../semantic-layer/
# / "aas" lands at .../semantic-layer/aas/ — where the JSON files live.
_AAS_DIR = Path(__file__).resolve().parent.parent.parent / "aas"

_AAS_FILES = [
    "aas_temp_humidity.json",
    "aas_lighting.json",
    "aas_gas.json",
    "aas_agv.json",
    "aas_counting.json",
]


# Core conversion: AAS JSON → RDFlib Graph

def load_aas_as_rdf() -> Graph:
    """Read all five AAS JSON descriptor files and return an RDFlib Graph.

    Triple shape produced for each subsystem:

        <urn:smart-factory:aas:gas>  rdf:type  sf:AssetAdministrationShell .
        <urn:smart-factory:aas:gas>  sf:globalAssetId  <urn:smart-factory:subsystem:gas> .
        <urn:smart-factory:aas:gas>  sf:hasSubmodel  <urn:smart-factory:aas:gas:submodel:OperationalData> .

        <urn:smart-factory:aas:gas:submodel:OperationalData>  rdf:type  sf:Submodel .
        <urn:smart-factory:aas:gas:submodel:OperationalData>  sf:semanticId  <sf:GasMonitoringSubsystem> .
        <urn:smart-factory:aas:gas:submodel:OperationalData>  sf:subsystem  "gas" .
        <urn:smart-factory:aas:gas:submodel:OperationalData>  sf:protocol  "modbus" .
        <urn:smart-factory:aas:gas:submodel:OperationalData>  sf:hasDevice  <sf:sensor_mq2_01> .
        <urn:smart-factory:aas:gas:submodel:OperationalData>  sf:hasObservableProperty  <sf:measuresSmoke> .
        ...
    """
    g = Graph()
    g.bind("sf", SF)

    for filename in _AAS_FILES:
        aas_path = _AAS_DIR / filename

        with open(aas_path, encoding="utf-8") as fh:
            aas = json.load(fh)

        # Shell-level triples
        shell_uri = URIRef(aas["id"])
        asset_uri = URIRef(aas["assetInformation"]["globalAssetId"])

        g.add((shell_uri, RDF.type, SF.AssetAdministrationShell))
        g.add((shell_uri, SF.globalAssetId, asset_uri))

        # One submodel per subsystem (all five JSON files follow this shape)
        for submodel in aas.get("submodels", []):

            # Unique URI for this submodel: <shell-id>:submodel:<idShort>
            submodel_uri = URIRef(f"{aas['id']}:submodel:{submodel['idShort']}")

            g.add((shell_uri, SF.hasSubmodel, submodel_uri))
            g.add((submodel_uri, RDF.type, SF.Submodel))

            # Link back to the ontology class (e.g. sf:GasMonitoringSubsystem)
            semantic_id = submodel.get("semanticId", "")
            if semantic_id:
                g.add((submodel_uri, SF.semanticId, URIRef(semantic_id)))

            # Subsystem name + protocol as plain strings
            g.add((submodel_uri, SF.subsystem, Literal(submodel.get("subsystem", ""))))
            g.add((submodel_uri, SF.protocol,   Literal(submodel.get("protocol",   ""))))

            # Every physical device ID listed in the descriptor
            for device_id in submodel.get("deviceIds", []):
                device_uri = URIRef(f"http://example.org/smart-factory#{device_id}")
                g.add((submodel_uri, SF.hasDevice, device_uri))

            # Every observable property the AAS declares (with its semantic URI)
            for prop in submodel.get("observedProperties", []):
                prop_uri = URIRef(prop["semanticUri"])
                g.add((submodel_uri, SF.hasObservableProperty, prop_uri))

    return g



# Helpers for the backend REST endpoint (no RDF needed by callers)

def get_aas_catalog() -> list[dict]:
    """Return a Python list with the index entries for all five AAS shells.

    Each entry has: id, idShort, subsystem, protocol, globalAssetId, file.
    Used by GET /api/v1/aas to return the catalogue without loading RDF.
    """
    index_path = _AAS_DIR / "aas_index.json"
    with open(index_path, encoding="utf-8") as fh:
        index = json.load(fh)
    return index["shells"]


def get_aas_descriptor(subsystem: str) -> dict | None:
    """Return the full AAS descriptor JSON for a single subsystem, or None.

    Example: get_aas_descriptor("gas") loads and returns aas_gas.json.
    Valid subsystem names: temp_humidity, lighting, gas, agv, counting.
    """
    catalog = get_aas_catalog()
    entry = next((s for s in catalog if s["subsystem"] == subsystem), None)
    if entry is None:
        return None
    descriptor_path = _AAS_DIR / entry["file"]
    with open(descriptor_path, encoding="utf-8") as fh:
        return json.load(fh)



# Fuseki write path

async def write_aas_to_fuseki(endpoint: str) -> bool:
    """Serialise all AAS triples to Turtle and POST them to a Fuseki endpoint.

    Returns True on HTTP 2xx, False on any error — never raises.
    Call this once at app startup to seed the knowledge graph with
    asset-level metadata so SPARQL can join it with live sensor observations.

    Example endpoint: "http://fuseki:3030/factory/data"
    """
    g = load_aas_as_rdf()
    turtle = g.serialize(format="turtle")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                endpoint,
                content=turtle.encode("utf-8"),
                headers={"Content-Type": "text/turtle"},
            )
        return 200 <= resp.status_code < 300
    except httpx.HTTPError:
        return False
