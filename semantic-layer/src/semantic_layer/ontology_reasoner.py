# activates RDFS+OWL RL reasoning over a local in-memory graph 

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS

logger = logging.getLogger(__name__)

SF    = Namespace("http://example.org/smart-factory#")
SAREF = Namespace("https://saref.etsi.org/core/")
SOSA  = Namespace("http://www.w3.org/ns/sosa/")

_ONTOLOGY_DIR = Path(__file__).resolve().parent / "ontology"


# Ontology loading

@lru_cache(maxsize=1)
def _load_tbox() -> Graph:
    tbox = Graph()
    for ttl in ["smart-factory.ttl", "saref-alignment.ttl"]:
        path = _ONTOLOGY_DIR / ttl
        if path.exists():
            tbox.parse(str(path), format="turtle")
        else:
            logger.warning("Ontology file not found: %s", path)
    logger.info("TBox loaded: %d triples", len(tbox))
    return tbox


# RDFS materialisation

def _apply_rdfs_rules(abox: Graph, tbox: Graph) -> Graph:
    merged = Graph()
    for triple in abox:
        merged.add(triple)
    for triple in tbox:
        merged.add(triple)

    changed = True
    iterations = 0
    max_iterations = 20 

    while changed and iterations < max_iterations:
        changed = False
        new_triples: list[tuple] = []

        for subj, _, superclass in tbox.triples((None, RDFS.subClassOf, None)):
            for instance in merged.subjects(RDF.type, subj):
                t = (instance, RDF.type, superclass)
                if t not in merged:
                    new_triples.append(t)

        for c1, _, c2 in tbox.triples((None, RDFS.subClassOf, None)):
            for _, _, c3 in tbox.triples((c2, RDFS.subClassOf, None)):
                t = (c1, RDFS.subClassOf, c3)
                if t not in merged:
                    new_triples.append(t)

        for p, _, q in tbox.triples((None, OWL.equivalentProperty, None)):
            for s, _, o in merged.triples((None, p, None)):
                t = (s, q, o)
                if t not in merged:
                    new_triples.append(t)
            for s, _, o in merged.triples((None, q, None)):
                t = (s, p, o)
                if t not in merged:
                    new_triples.append(t)

        for c1, _, c2 in tbox.triples((None, OWL.equivalentClass, None)):
            for inst in merged.subjects(RDF.type, c1):
                t = (inst, RDF.type, c2)
                if t not in merged:
                    new_triples.append(t)
            for inst in merged.subjects(RDF.type, c2):
                t = (inst, RDF.type, c1)
                if t not in merged:
                    new_triples.append(t)

        for triple in new_triples:
            merged.add(triple)
            changed = True
        iterations += 1

    logger.debug(
        "RDFS materialisation: %d iterations, %d total triples",
        iterations, len(merged)
    )
    return merged


# Public API 

def reason(abox: Graph, use_pyshacl_rdfs: bool = False) -> Graph:
    tbox = _load_tbox()

    if use_pyshacl_rdfs:
        try:
            import pyshacl
            enriched = Graph()
            for t in abox:
                enriched.add(t)
            pyshacl.validate(
                enriched,
                shacl_graph=None,
                ont_graph=tbox,
                inference="rdfs",
                inplace=True,
                abort_on_first=False,
            )
            logger.debug("pyshacl RDFS inference applied: %d triples", len(enriched))
            return enriched
        except ImportError:
            logger.warning("pyshacl not available — falling back to built-in RDFS rules")

    return _apply_rdfs_rules(abox, tbox)


def query_with_inference(
    abox: Graph,
    sparql: str,
    use_pyshacl_rdfs: bool = False,
) -> list[dict]:
    enriched = reason(abox, use_pyshacl_rdfs=use_pyshacl_rdfs)
    results = []
    for row in enriched.query(sparql):
        results.append({str(var): str(val) for var, val in zip(row.labels, row)})
    return results


def inferred_classes(abox: Graph, entity: URIRef) -> list[URIRef]:
    enriched = reason(abox)
    return [
        o for o in enriched.objects(entity, RDF.type)
        if isinstance(o, URIRef)
    ]