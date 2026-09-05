# XA-202606 Smart Factory Safety Platform

This project normalises factory sensor data from MQTT, REST, Modbus TCP, and
OPC UA into one strict message contract. Accepted observations can be persisted
to SQLite and an RDF knowledge graph, evaluated by safety rules, and shown in a
Vue dashboard.

## What is genuinely ontology-driven

`bindings.ttl` is the source of truth for device IDs, protocol addresses,
units, scaling, Modbus function/slave IDs, MQTT topics, REST routes, and OPC UA
nodes. The live Modbus, MQTT, and OPC UA adapters build their runtime plans from
a validated binding registry. Duplicate identifiers and overlapping Modbus
wire addresses are rejected atomically.

Adding a device that uses **existing measurement and unit types** requires one
binding change and regeneration. On openEuler, `sudo xa202606-reload` validates
the files and reloads the backend, binding service, and active adapters without
restarting their processes. Adding a new measurement or unit type still
requires changes to the strict Python contract, semantic mapping, ontology,
and tests; an ontology fragment alone is insufficient.

## Local setup

Requirements: Python 3.11+, Node.js 20+, and optionally Apache Jena Fuseki and
Mosquitto.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e shared -e backend -e connectivity -e analytics -e semantic-layer
cd dashboard && npm install && cd ..
```

Set at least:

```dotenv
API_KEY=replace-with-a-random-api-key
COMMAND_SIGNING_KEY=replace-with-a-separate-device-command-key
```

Enable knowledge-graph writes explicitly with
`SEMANTIC_WRITE_ENABLED=true`. Otherwise Fuseki is optional and the backend
runs in degraded semantic mode.

Start the backend from the repository root so it can find `bindings.ttl`:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Then start the dashboard:

```bash
cd dashboard
npm run dev
```

For Docker Compose, Modbus and OPC UA services are in the `hardware` profile
because this repository does not include working simulators for them:

```bash
docker compose -f deploy/docker-compose.yml --profile hardware up -d --build
```

Configure `MODBUS_HOST`, `MODBUS_PORT`, and `OPCUA_ENDPOINT` for the actual
factory endpoints.

## Bindings and generated adapters

```bash
python scripts/generate_adapters.py
python scripts/generate_adapters.py --check
```

The generated files are committed for review. Runtime adapters use the same
validated registry rather than separate device-specific maps.

## Verification

```bash
python -m pytest backend/tests connectivity/tests semantic-layer/tests analytics/tests shared/tests benchmark/tests -q
cd firmware && python -m pytest tests -q && cd ..
cd dashboard && npm test -- --run && npm run build && cd ..
python validation/run_validation.py
python validation/run_benchmark.py
python scripts/validate_sample_data.py
```

## openEuler deployment

The supported domestic-OS target is openEuler 24.03 LTS on x86_64 or AArch64.
See `deploy/openeuler/README.md` for native systemd installation, offline wheel
support, coordinated runtime reload, verification, and OPC UA certificates.
The committed installer is not a substitute for retaining logs from the actual
target machine.

## Current limitations

- Reference acquisition firmware is present for all five boards, but it has not
  been compiled, flashed, wired, calibrated, or validated in this environment.
- There is no full physical-hardware end-to-end test or retained execution
  evidence from the target openEuler machine.
- Sensor accuracy, collection latency, cross-platform communication efficiency,
  CPU/memory use, and soak stability have not been measured.
- OPC UA supports Basic256Sha256 SignAndEncrypt, pinned server certificates,
  username credentials, and optional X.509 user identity. Field certificate
  issuance, server trust-list configuration, and target-network testing remain.
- The repository does not yet include the required competition PPT, demo video,
  complete design/development/test documents, summary report, or signed formal
  declaration. A declaration checklist template is included under `docs/`.

See `docs/competition-requirements-audit.md` for the detailed competition gap
assessment and evidence plan.
