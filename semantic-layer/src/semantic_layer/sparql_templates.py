# SPARQL query templates for the knowledge graph.

_PREFIXES = (
    "PREFIX sosa: <http://www.w3.org/ns/sosa/>\n"
    "PREFIX sf:   <http://example.org/smart-factory#>\n"
    "PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>\n"
    "PREFIX prov: <http://www.w3.org/ns/prov#>\n"
)

def latest_by_device(device_id: str, limit: int = 10) -> str:
    
    device_uri = f"http://example.org/smart-factory#{device_id}"
    return (
        _PREFIXES +
        "SELECT ?prop ?value ?unit ?time WHERE {\n"
        "  ?obs a sosa:Observation ;\n"
        f"       sosa:madeBySensor <{device_uri}> ;\n"
        "       sosa:observedProperty ?prop ;\n"
        "       sosa:hasSimpleResult ?value ;\n"
        "       sosa:resultTime ?time .\n"
        "  OPTIONAL { ?obs sf:hasUnit ?unit }\n"
        "}\n"
        f"ORDER BY DESC(?time) LIMIT {int(limit)}"
    )


def observations_in_window(minutes: int = 30) -> str:
    
    return (
        _PREFIXES +
        "SELECT ?sensor ?prop ?value ?time ?subsystem WHERE {\n"
        "  ?obs a sosa:Observation ;\n"
        "       sosa:madeBySensor ?sensor ;\n"
        "       sosa:observedProperty ?prop ;\n"
        "       sosa:hasSimpleResult ?value ;\n"
        "       sosa:resultTime ?time .\n"
        "  OPTIONAL { ?sensor sf:belongsToSubsystem ?subsystem }\n"
        f"  FILTER(?time >= xsd:dateTime(NOW() - \"PT{int(minutes)}M\"^^xsd:duration))\n"
        "}\n"
        "ORDER BY ?sensor DESC(?time)"
    )


def subsystem_summary() -> str:
    
    return (
        _PREFIXES +
        "SELECT ?subsystem (COUNT(DISTINCT ?sensor) AS ?sensorCount) "
        "(COUNT(DISTINCT ?prop) AS ?propCount) WHERE {\n"
        "  ?sensor sf:belongsToSubsystem ?subsystem .\n"
        "  ?obs sosa:madeBySensor ?sensor ;\n"
        "       sosa:observedProperty ?prop .\n"
        "}\n"
        "GROUP BY ?subsystem\n"
        "ORDER BY ?subsystem"
    )


def device_property_matrix() -> str:
    
    return (
        _PREFIXES +
        "SELECT ?sensor ?subsystem ?protocol ?prop WHERE {\n"
        "  ?obs a sosa:Observation ;\n"
        "       sosa:madeBySensor ?sensor ;\n"
        "       sosa:observedProperty ?prop .\n"
        "  OPTIONAL { ?sensor sf:belongsToSubsystem ?subsystem }\n"
        "  OPTIONAL { ?sensor sf:transportedVia ?protocol }\n"
        "}\n"
        "GROUP BY ?sensor ?subsystem ?protocol ?prop\n"
        "ORDER BY ?sensor ?prop"
    )


def cross_subsystem_correlation(prop_a: str, prop_b: str,
                                minutes: int = 10) -> str:
    
    uri_a = f"http://example.org/smart-factory#{prop_a}"
    uri_b = f"http://example.org/smart-factory#{prop_b}"

    return (
        _PREFIXES +
        "SELECT ?sensorA ?valueA ?timeA ?sensorB ?valueB ?timeB WHERE {\n"
        "  ?obsA a sosa:Observation ;\n"
        "        sosa:madeBySensor ?sensorA ;\n"
        f"        sosa:observedProperty <{uri_a}> ;\n"
        "        sosa:hasSimpleResult ?valueA ;\n"
        "        sosa:resultTime ?timeA .\n"
        "  ?obsB a sosa:Observation ;\n"
        "        sosa:madeBySensor ?sensorB ;\n"
        f"        sosa:observedProperty <{uri_b}> ;\n"
        "        sosa:hasSimpleResult ?valueB ;\n"
        "        sosa:resultTime ?timeB .\n"
        # different sensors
        "  FILTER(?sensorA != ?sensorB)\n"
        # within the same time window
        f"  FILTER(?time >= xsd:dateTime(NOW() - \"PT{int(minutes)}M\"^^xsd:duration))\n"
        "}\n"
        "ORDER BY DESC(?timeA) LIMIT 20"
    )


def provenance_trace(device_id: str) -> str:
    
    device_uri = f"http://example.org/smart-factory#{device_id}"
    return (
        _PREFIXES +
        "SELECT ?obs ?prop ?value ?agent ?ingestedAt WHERE {\n"
        f"  ?obs sosa:madeBySensor <{device_uri}> ;\n"
        "       sosa:observedProperty ?prop ;\n"
        "       sosa:hasSimpleResult ?value .\n"
        "  OPTIONAL { ?obs prov:wasAttributedTo ?agent }\n"
        "  OPTIONAL { ?obs prov:generatedAtTime ?ingestedAt }\n"
        "}\n"
        "ORDER BY DESC(?ingestedAt) LIMIT 20"
    )

NAMED_QUERIES = {
    "subsystem-summary":      subsystem_summary,
    "device-property-matrix":  device_property_matrix,
}
