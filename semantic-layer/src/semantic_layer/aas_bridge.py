import json
from pathlib import Path

import httpx
from rdflib import RDF, Graph, Literal, Namespace, URIRef

SF = Namespace("http://example.org/smart-factory#")

_AAS_DIR = Path(__file__).resolve().parent / "aas"
if not _AAS_DIR.exists():
    _AAS_DIR = Path(__file__).resolve().parent.parent.parent / "aas"

_AAS_FILES = [
    "aas_temp_humidity.json",
    "aas_lighting.json",
    "aas_gas.json",
    "aas_agv.json",
    "aas_counting.json",
]




def load_aas_as_rdf() -> Graph:
    pass















    g = Graph()
    g.bind("sf", SF)

    for filename in _AAS_FILES:
        aas_path = _AAS_DIR / filename

        with open(aas_path, encoding="utf-8") as fh:
            aas = json.load(fh)

        
        shell_uri = URIRef(aas["id"])
        asset_uri = URIRef(aas["assetInformation"]["globalAssetId"])

        g.add((shell_uri, RDF.type, SF.AssetAdministrationShell))
        g.add((shell_uri, SF.globalAssetId, asset_uri))

        
        for submodel in aas.get("submodels", []):
            
            submodel_uri = URIRef(f"{aas['id']}:submodel:{submodel['idShort']}")

            g.add((shell_uri, SF.hasSubmodel, submodel_uri))
            g.add((submodel_uri, RDF.type, SF.Submodel))

            semantic_id = submodel.get("semanticId", "")
            if semantic_id:
                g.add((submodel_uri, SF.semanticId, URIRef(semantic_id)))

            g.add((submodel_uri, SF.subsystem, Literal(submodel.get("subsystem", ""))))
            g.add((submodel_uri, SF.protocol, Literal(submodel.get("protocol", ""))))

            for device_id in submodel.get("deviceIds", []):
                device_uri = URIRef(f"http://example.org/smart-factory#{device_id}")
                g.add((submodel_uri, SF.hasDevice, device_uri))

            for prop in submodel.get("observedProperties", []):
                prop_uri = URIRef(prop["semanticUri"])
                g.add((submodel_uri, SF.hasObservableProperty, prop_uri))

    return g





def get_aas_catalog() -> list[dict]:
    pass
    index_path = _AAS_DIR / "aas_index.json"
    with open(index_path, encoding="utf-8") as fh:
        index = json.load(fh)
    return index["shells"]


def get_aas_descriptor(subsystem: str) -> dict | None:
    pass
    catalog = get_aas_catalog()
    entry = next((s for s in catalog if s["subsystem"] == subsystem), None)
    if entry is None:
        return None
    descriptor_path = _AAS_DIR / entry["file"]
    with open(descriptor_path, encoding="utf-8") as fh:
        return json.load(fh)





async def write_aas_to_fuseki(endpoint: str) -> bool:
    pass




    g = load_aas_as_rdf()
    turtle = g.serialize(format="turtle")

    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            resp = await client.post(
                endpoint,
                content=turtle.encode("utf-8"),
                headers={"Content-Type": "text/turtle"},
            )
        return 200 <= resp.status_code < 300
    except httpx.HTTPError:
        return False
