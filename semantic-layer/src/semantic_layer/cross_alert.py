import httpx

TEMP_THRESHOLD = 35.0
GAS_THRESHOLD = 35.0

_QUERY = (
    "PREFIX sosa: <http://www.w3.org/ns/sosa/> "
    "PREFIX sf:   <http://example.org/smart-factory#> "
    "SELECT ?tempSensor ?tempVal ?gasSensor ?gasVal WHERE { "
    "  ?t a sosa:Observation ; "
    "     sosa:madeBySensor ?tempSensor ; "
    "     sosa:observedProperty sf:measuresTemperature ; "
    "     sosa:hasSimpleResult ?tempVal . "
    "  ?g a sosa:Observation ; "
    "     sosa:madeBySensor ?gasSensor ; "
    "     sosa:observedProperty ?gasProp ; "
    "     sosa:hasSimpleResult ?gasVal . "
    "  VALUES ?gasProp { sf:measuresCO sf:measuresSmoke sf:measuresCombustibleGas } "
    f" FILTER(?tempVal > {TEMP_THRESHOLD}) "
    f" FILTER(?gasVal  > {GAS_THRESHOLD}) "
    "} LIMIT 1"
)


def _local(uri: str) -> str:
    return uri.rsplit("#", 1)[-1] if "#" in uri else uri.rsplit("/", 1)[-1]


async def check_fire_risk(fuseki_url: str) -> dict | None:
    """Query Fuseki for a simultaneous high-temperature + high-gas condition."""
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            resp = await client.post(
                fuseki_url,
                content=_QUERY.encode(),
                headers={
                    "Content-Type": "application/sparql-query",
                    "Accept": "application/sparql-results+json",
                },
            )
        resp.raise_for_status()
        bindings = resp.json()["results"]["bindings"]
    except httpx.HTTPError:
        return None

    if not bindings:
        return None

    row = bindings[0]
    return {
        "risk": "fire",
        "temp_sensor": _local(row["tempSensor"]["value"]),
        "temp_val": float(row["tempVal"]["value"]),
        "gas_sensor": _local(row["gasSensor"]["value"]),
        "gas_val": float(row["gasVal"]["value"]),
        "thresholds": {"temperature": TEMP_THRESHOLD, "gas": GAS_THRESHOLD},
    }
