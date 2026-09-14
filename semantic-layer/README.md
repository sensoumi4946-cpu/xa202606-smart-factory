# Semantic Layer

The semantic layer provides the ontology/binding model, SHACL gating, RDF mapping, AAS views and SPARQL/Fuseki integration.

## Core responsibilities

- parse and validate `bindings.ttl`
- map validated observations to RDF
- execute SHACL constraints
- maintain ontology/AAS semantic views
- publish/query RDF through Fuseki
- provide SPARQL templates and query services
- support semantic provenance and conformance checks

## Critical-path boundary

SHACL gate validation is part of the ingest correctness path.

Fuseki persistence/query is a semantic service and may degrade independently; loss of Fuseki must not stop core ingestion and local safety analysis.

```text
UnifiedMessage
      ↓
binding + semantic mapping
      ↓
SHACL
  ├─ invalid → reject
  └─ valid
       ↓
    business persistence / analytics
       ↓
    RDF/Fuseki background path
```

## Binding-driven generation

`bindings.ttl` is also consumed by the adapter-generation workflow. Invalid or conflicting bindings must fail before a new generated adapter set is accepted.

```bash
python scripts/generate_adapters.py
python scripts/generate_adapters.py --check
```

## Fuseki

Typical query endpoint:

```text
http://localhost:3030/factory/query
```

Semantic writes are controlled by environment configuration such as:

```bash
SEMANTIC_WRITE_ENABLED=true
FUSEKI_ENDPOINT=http://localhost:3030/factory/data
FUSEKI_QUERY_URL=http://localhost:3030/factory/query
```

## Test

```bash
python -m pytest semantic-layer/tests -q
```
