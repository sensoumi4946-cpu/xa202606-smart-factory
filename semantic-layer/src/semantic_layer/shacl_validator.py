# Semantic observation validator  

from rdflib import RDF, SOSA, Graph


def validate_observation_graph(g: Graph) -> tuple[bool, list[str]]:
    """Check that every sosa:Observation in g has all four required predicates.
    """
    errors: list[str] = []

    observations = list(g.subjects(RDF.type, SOSA.Observation))

    if not observations:
        errors.append(
            "Graph contains zero sosa:Observation nodes — "
            "mapping.to_rdf_graph() may have returned an empty graph."
        )
        return False, errors

    # Check each observation individually
    for obs_uri in sorted(observations, key=str):
        label = str(obs_uri)

        if not list(g.objects(obs_uri, SOSA.madeBySensor)):
            errors.append(f"{label}: missing sosa:madeBySensor")

        if not list(g.objects(obs_uri, SOSA.observedProperty)):
            errors.append(f"{label}: missing sosa:observedProperty")

        results = list(g.objects(obs_uri, SOSA.hasSimpleResult))
        if not results:
            errors.append(f"{label}: missing sosa:hasSimpleResult")
        else:
            for r in results:
                try:
                    float(r)
                except (TypeError, ValueError):
                    errors.append(
                        f"{label}: sosa:hasSimpleResult value '{r}' is not numeric"
                    )

        if not list(g.objects(obs_uri, SOSA.resultTime)):
            errors.append(f"{label}: missing sosa:resultTime")

    return (len(errors) == 0), errors


def validate_and_explain(g: Graph) -> str:
    """Return a one-line summary of the validation result.

    """
    valid, errors = validate_observation_graph(g)

    if valid:
        obs_count = sum(1 for _ in g.subjects(RDF.type, SOSA.Observation))
        return f"Valid — {obs_count} observation(s) passed all checks."

    lines = [f"Invalid — {len(errors)} violation(s):"]
    lines += [f"  • {e}" for e in errors]
    return "\n".join(lines)
