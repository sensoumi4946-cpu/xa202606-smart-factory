# semantic-layer/src/semantic_layer/shacl_validator.py
#
# ─────────────────────────────────────────────────────────────────────────────
# Semantic observation validator  (YOUR contribution)
# ─────────────────────────────────────────────────────────────────────────────
#
# What this file does, in plain English:
#   Before writing an RDF observation to Fuseki, we should check that it is
#   well-formed — otherwise the knowledge graph fills up with garbage triples
#   that break SPARQL queries.
#
#   In the semantic web world, the formal way to express "an Observation MUST
#   have a sensor, a property, a result, and a timestamp" is a SHACL shape.
#   This module implements those same four constraints in plain Python using
#   rdflib (which is already a dependency — no new packages needed).
#
# What counts as a valid sosa:Observation here:
#   ✓  sosa:madeBySensor    → which physical device produced this reading
#   ✓  sosa:observedProperty → what quantity was measured (temperature, CO, …)
#   ✓  sosa:hasSimpleResult  → the numeric value (must be castable to float)
#   ✓  sosa:resultTime       → ISO-8601 timestamp string
#
# How to use it:
#   from semantic_layer.shacl_validator import validate_observation_graph
#   ok, errors = validate_observation_graph(graph)
#   if not ok:
#       for msg in errors:
#           print("VALIDATION ERROR:", msg)
#
# In the ingest pipeline you could call this between mapping.to_rdf_graph()
# and fuseki.write_to_fuseki() so only valid triples ever reach the graph.

from rdflib import RDF, SOSA, Graph


def validate_observation_graph(g: Graph) -> tuple[bool, list[str]]:
    """Check that every sosa:Observation in g has all four required predicates.

    Args:
        g: An RDFlib Graph, typically produced by mapping.to_rdf_graph().

    Returns:
        (True, [])            — if the graph is fully valid
        (False, [error, …])   — if any constraint is violated;
                                 the list contains one human-readable string
                                 per violation, prefixed with the observation URI.
    """
    errors: list[str] = []

    # Find every node that is declared as a sosa:Observation
    observations = list(g.subjects(RDF.type, SOSA.Observation))

    if not observations:
        errors.append(
            "Graph contains zero sosa:Observation nodes — "
            "mapping.to_rdf_graph() may have returned an empty graph."
        )
        return False, errors

    # Check each observation individually
    for obs_uri in sorted(observations, key=str):
        label = str(obs_uri)  # use the full URI as a readable name in errors

        # ── Constraint 1: must have a sensor ──────────────────────────────────
        if not list(g.objects(obs_uri, SOSA.madeBySensor)):
            errors.append(f"{label}: missing sosa:madeBySensor")

        # ── Constraint 2: must have an observed property ──────────────────────
        if not list(g.objects(obs_uri, SOSA.observedProperty)):
            errors.append(f"{label}: missing sosa:observedProperty")

        # ── Constraint 3: must have a numeric result ──────────────────────────
        results = list(g.objects(obs_uri, SOSA.hasSimpleResult))
        if not results:
            errors.append(f"{label}: missing sosa:hasSimpleResult")
        else:
            for r in results:
                try:
                    float(r)  # rdflib XSD.double Literals support float()
                except (TypeError, ValueError):
                    errors.append(
                        f"{label}: sosa:hasSimpleResult value '{r}' is not numeric"
                    )

        # ── Constraint 4: must have a timestamp ───────────────────────────────
        if not list(g.objects(obs_uri, SOSA.resultTime)):
            errors.append(f"{label}: missing sosa:resultTime")

    return (len(errors) == 0), errors


def validate_and_explain(g: Graph) -> str:
    """Return a one-line human-readable summary of the validation result.

    Useful for logging: log_json("semantic_validation", result=validate_and_explain(g))

    Examples:
        "✓ Valid — 2 observation(s) passed all checks."
        "✗ Invalid — 1 violation(s):\n  • obs_abc123: missing sosa:resultTime"
    """
    valid, errors = validate_observation_graph(g)

    if valid:
        obs_count = sum(1 for _ in g.subjects(RDF.type, SOSA.Observation))
        return f"✓ Valid — {obs_count} observation(s) passed all checks."

    lines = [f"✗ Invalid — {len(errors)} violation(s):"]
    lines += [f"  • {e}" for e in errors]
    return "\n".join(lines)
