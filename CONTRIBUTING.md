# XA-202606 Smart Factory Platform — Developer Guide

## Overview

This monorepo implements the **initial scaffold** of the XA-202606 Smart Factory Safety Monitoring & Control Platform. It establishes a **minimum viable data pipeline**: mock sensor data flows through an MQTT broker, a protocol adapter normalises it into a unified format, a backend persists it to SQLite, and a Vue dashboard displays it. No real hardware, no semantic reasoning, no control actuation — just a proven, test-covered skeleton ready for expansion.

### Architecture (Current)

```
Mock Generator ──MQTT──▶ Mosquitto Broker ──MQTT──▶ Connectivity Adapter ──HTTP──▶ Backend API ──▶ SQLite
                                                      │                                      │
                                                      └── UnifiedMessage contract            ├── Dashboard (Vue 3)
                                                                                             └── Semantic Layer (Turtle ontology)
```

| Layer | Directory | Runtime | Port |
|---|---|---|---|
| Data contract (shared) | `shared/` | Import-only | — |
| Backend API | `backend/` | FastAPI + SQLite | 8000 |
| Connectivity | `connectivity/` | MQTT adapter → HTTP forward | — |
| Mock generator | `analytics/mock/` | CLI tool | — |
| Semantic vocabulary | `semantic-layer/` | Turtle file (static) | — |
| Dashboard | `dashboard/` | Vue 3 + Vite | 5173 |
| Infrastructure | `deploy/` | Docker Compose (4 services) | — |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 22 (for the dashboard)
- Docker + Docker Compose (optional, for containerised run)
- `uv` or `pip` (Python package manager)

### 1. Install dependencies

```bash
pip install -e shared/ -e backend/[dev] -e connectivity/[dev] -e analytics/[dev] -e semantic-layer/[dev]
cd dashboard && npm install && cd ..
```

### 2. Run tests (48 tests, ~12 seconds)

```bash
pytest shared/tests/ backend/tests/ connectivity/tests/ analytics/tests/ semantic-layer/tests/ -v
```

### 3. Start the full stack (Docker)

```bash
docker compose -f deploy/docker-compose.yml up -d
```

This starts Mosquitto (1883), Backend (8000), Connectivity, and Dashboard (5173).

### 4. Push mock data

```bash
python -m analytics.mock.generator --count 5
```

### 5. Verify

```bash
curl http://localhost:8000/health                    # → {"status":"ok"}
curl http://localhost:8000/api/v1/devices            # → ["sensor_dht22_01", ...]
curl "http://localhost:8000/api/v1/data?device_id=sensor_dht22_01&limit=3"
```

Open `http://localhost:5173` to see the dashboard.

---

## UnifiedMessage Contract

This is the **single wire format** for all sensor data in the platform. Every protocol adapter MUST output this structure. It is defined once in `shared/src/smart_factory_contracts/messages.py`.

```python
class UnifiedMessage(BaseModel):
    schema_version: Literal["v1"]          # REQUIRED — clients must declare version
    device_id: str                         # e.g. "sensor_dht22_01"
    subsystem: Subsystem                   # "temp_humidity" | "lighting" | "gas" | "agv" | "counting"
    protocol: Protocol                     # "mqtt" | "modbus" | "opcua" | "rest" | "mock"
    timestamp: datetime                    # UTC ISO 8601, auto-generated if omitted
    measurements: list[Measurement]        # at least one
    raw_payload: Optional[dict]            # original bytes for debugging
```

### Measurement

```python
class Measurement(BaseModel):
    type: MeasurementType                  # "temperature" | "humidity" | "co" | "smoke" | "combustible_gas" | "distance" | "count" | "occupancy" | "light_state"
    value: float
    unit: Unit                             # "celsius" | "percent" | "ppm" | "cm" | "count" | "boolean"
```

### Five Subsystems

| Subsystem Enum | Sensor | Measurements |
|---|---|---|
| `temp_humidity` | DHT22 | temperature (celsius), humidity (percent) |
| `lighting` | PIR | occupancy (boolean), light_state (boolean) |
| `gas` | MQ-2/MQ-7 | smoke (ppm), co (ppm), combustible_gas (ppm) |
| `agv` | HC-SR04 | distance (cm) |
| `counting` | IR break-beam | count (count) |

---

## MQTT Topic Protocol

```
factory/{subsystem}/sensors/{device_id}/{measurement_type}

Examples:
  factory/temp_humidity/sensors/sensor_dht22_01/temperature
  factory/gas/sensors/sensor_mq2_01/co
  factory/counting/sensors/sensor_ir_01/count
```

**Subscription wildcard** used by the connectivity adapter: `factory/+/sensors/#`

**Control topics** are reserved for future development and are **explicitly filtered** out of the sensor data pipeline:
```
factory/{subsystem}/control/{device_id}/{action}
```

---

## Backend API Reference

| Method | Path | Purpose | Request Body | Response |
|---|---|---|---|---|
| `GET` | `/health` | Health check | — | `200 {"status":"ok"}` |
| `POST` | `/api/v1/data` | Ingest sensor data | `UnifiedMessage` | `201 {"id":"uuid"}` |
| `GET` | `/api/v1/data` | Query sensor data | Query: `device_id`, `limit` (1-1000), `since` (ISO 8601) | `200 [rows...]` |
| `GET` | `/api/v1/devices` | List known device IDs | — | `200 ["id1","id2"]` |
| `POST` | `/api/v1/control` | Issue control command | `{"device_id":str,"action":str,"params":{}}` | `202 {"command_id":"uuid"}` |
| `GET` | `/api/v1/control/{id}` | Check command status | — | `200 {"status":"pending"}` |

---

## Storage Schema (SQLite)

```sql
-- Current — designed for easy migration to InfluxDB/IoTDB later
CREATE TABLE sensor_data (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    subsystem TEXT NOT NULL,
    protocol TEXT NOT NULL,
    timestamp TEXT NOT NULL,         -- ISO 8601 UTC
    measurements TEXT NOT NULL,      -- JSON array of Measurement
    raw_payload TEXT,                -- nullable, original wire bytes
    ingested_at TEXT NOT NULL        -- server-side ingestion timestamp
);

CREATE TABLE control_commands (
    command_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    action TEXT NOT NULL,
    params TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);
```

---

## Semantic Ontology (smart-factory.ttl)

The Turtle file in `semantic-layer/src/semantic_layer/ontology/` defines the **shared vocabulary** using SOSA/SSN standards:

- **6 Sensor classes**: TemperatureSensor, HumiditySensor, GasSensor, ProximitySensor, CountSensor, OccupancySensor
- **9 ObservableProperties**: measuresTemperature, measuresHumidity, measuresCO, measuresSmoke, measuresCombustibleGas, measuresDistance, measuresCount, measuresOccupancy, measuresLightState
- **5 Subsystem groupings**: TempHumiditySubsystem, LightingSubsystem, GasMonitoringSubsystem, AGVObstacleSubsystem, CountingSubsystem

Currently only validates that the file is parseable by RDFlib. Semantic mapping and SPARQL querying come later.

---

## Logging Convention

All services output **JSON Lines** (one JSON object per line) to stdout. Each log entry includes at minimum:

```json
{"service": "connectivity", "event": "message_parsed", "level": "info",
 "timestamp": "2026-07-01T12:00:00+00:00", "device_id": "sensor_dht22_01", ...}
```

Errors go to stderr. Container log aggregation tools (Docker, Loki, Fluentd) can consume this directly.

---

## Project Conventions

| Rule | Detail |
|---|---|
| Python version | 3.11+ |
| Package layout | `src/<package>/...` (all five packages) |
| Contract ownership | `UnifiedMessage` lives ONLY in `shared/`; all others import it |
| Configuration | Environment variables only; `.env` never committed |
| Timezone | All timestamps UTC ISO 8601 |
| Ports | Registered in `docs/port-registry.md` before use |
| Branch naming | Short, descriptive: `feat/monorepo-scaffold`, not `phase-1-...` |
| Commit style | Conventional Commits (English): `feat:`, `fix:`, `docs:` |

---

## Toolchain

| Concern | Tool | Command |
|---|---|---|
| Python package management | `uv` or `pip` | `pip install -e ...` |
| Python formatting | Ruff | `ruff format src/` |
| Python testing | pytest | `pytest tests/ -v` |
| Node package management | npm | `npm install` |
| Frontend testing | Vitest | `npm test` |
| Container orchestration | Docker Compose | `docker compose up -d` |
| One-shot everything | Makefile | `make test`, `make up`, `make lint` |

---

## Directory Map

```
xa202606-smart-factory/
├── shared/                        Data contracts (imported by all)
│   ├── pyproject.toml
│   ├── src/smart_factory_contracts/
│   │   ├── __init__.py            Public API re-exports
│   │   ├── messages.py            UnifiedMessage, Measurement, 6 enums
│   │   └── py.typed               PEP 561 marker
│   └── tests/test_messages.py     9 tests
│
├── backend/                       FastAPI + SQLite
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── src/backend/
│   │   ├── main.py                App factory + lifespan + error handler
│   │   ├── config.py              Env-var config
│   │   ├── models.py              API request/response Pydantic models
│   │   ├── store.py               SQLite CRUD (monkeypatch-friendly)
│   │   └── api/                   ingest.py / query.py / control.py
│   └── tests/                     13 tests
│
├── connectivity/                  Protocol adapters
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── src/connectivity/
│   │   ├── runner.py              MQTT adapter entry point
│   │   ├── models.py              Config
│   │   ├── router.py              HTTP forwarder with retry
│   │   └── adapters/
│   │       ├── base.py            Abstract adapter ABC
│   │       ├── mqtt_adapter.py    Full MQTT implementation
│   │       ├── modbus_adapter.py  Skeleton
│   │       ├── opcua_adapter.py   Skeleton
│   │       └── rest_adapter.py    Skeleton
│   └── tests/                     11 tests
│
├── analytics/                     Mock data & future analysis
│   ├── pyproject.toml
│   ├── src/analytics/mock/
│   │   └── generator.py           CLI mock data generator
│   └── tests/test_generator.py    8 tests
│
├── semantic-layer/                Shared vocabulary
│   ├── pyproject.toml
│   ├── src/semantic_layer/
│   │   └── ontology/
│   │       └── smart-factory.ttl  Turtle file (SOSA/SSN)
│   └── tests/test_ontology_parse.py  5 tests
│
├── dashboard/                     Vue 3 frontend
│   ├── package.json
│   ├── vite.config.ts             Proxy /api → backend:8000
│   ├── index.html
│   └── src/
│       ├── main.ts                Vue app bootstrap
│       ├── App.vue                Device selector + JSON display
│       └── api.ts                 Typed fetch wrappers
│
├── deploy/                        Infrastructure
│   ├── docker-compose.yml         4 services (mosquitto, backend, connectivity, dashboard)
│   ├── mqtt/mosquitto.conf        Anonymous access, stdout logging
│   └── .env.example
│
├── Makefile                       up / down / test / lint / clean
├── .env.example                   All configurable env vars
└── .devcontainer/                 VS Code / GitHub Codespaces
```

---

## Completion Criteria

- [x] Mock generator publishes to MQTT for all 5 subsystems
- [x] MQTT adapter subscribes `factory/+/sensors/#` and parses payloads
- [x] Backend ingests, stores (SQLite), and queries sensor data
- [x] Control API records commands as pending
- [x] Dashboard connects to backend and displays JSON
- [x] Docker Compose one-command startup
- [x] 48 automated tests passing
- [x] Turtle ontology parseable by RDFlib
- [ ] Real hardware integration (future)
- [ ] Full Modbus / OPC UA / REST adapters (future)
- [ ] Frontend ECharts visualisation (future)
- [ ] Semantic runtime with AAS + SPARQL (future)
- [ ] Real device control actuation (future)
