# Fuseki write path — turns a UnifiedMessage into Turtle and POSTs it to
# a Jena Fuseki Graph Store endpoint.
#
# This is the runtime bridge between the backend ingest pipeline and the
# persistent knowledge graph. It reuses mapping.py for the RDF conversion
# so the triple shape stays identical to the pytest-verified local path.
#
# Every network error (unreachable host, timeout, non-2xx) is swallowed and
# reported as a bool — the caller treats semantic persistence as best-effort
# and never lets a Fuseki outage break sensor ingestion.
import httpx
from rdflib import SOSA, Namespace
from smart_factory_contracts.messages import UnifiedMessage

from semantic_layer.mapping import SF, to_rdf_graph

_TIMEOUT = 5.0


def to_turtle(msg: UnifiedMessage) -> str:
    """Serialise a UnifiedMessage to a Turtle string via to_rdf_graph()."""
    g = to_rdf_graph(msg)
    g.bind("sosa", SOSA)
    g.bind("sf", Namespace(SF))
    return g.serialize(format="turtle")


async def write_to_fuseki(msg: UnifiedMessage, endpoint: str) -> bool:
    """POST Turtle to a Fuseki /data endpoint. True on 2xx, False otherwise.

    Connection failures and timeouts are caught and reported as False so the
    caller can log a best-effort warning without raising.
    """
    turtle = to_turtle(msg)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, trust_env=False) as client:
            resp = await client.post(
                endpoint,
                content=turtle.encode("utf-8"),
                headers={"Content-Type": "text/turtle"},
            )
        return 200 <= resp.status_code < 300
    except httpx.HTTPError:
        return False
