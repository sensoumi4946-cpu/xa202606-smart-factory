# XA-202606 Smart Factory Platform — Developer Guide

## Overview

This monorepo implements the XA-202606 Smart Factory Safety Monitoring & Control Platform. It features a **tab-based console dashboard** (monitoring / API debugging / device management / system status), a **rule-based alert engine**, **multi-protocol adapters** (MQTT / REST / Modbus / OPC UA) for heterogeneous device normalisation, a **Fuseki-powered semantic runtime** with SOSA/SSN for cross-device SPARQL queries, and **AAS digital-twin descriptors** — all running on a Docker Compose stack.

### Architecture

```
                      ┌──▶ MQTT Adapter ──────┐
MQTT Sim ──▶ Mosquitto┤                        │
                      ┌──▶ REST Adapter ───────┤
REST Pusher ──────────┤                        ├──▶ Backend API ──▶ SQLite
Modbus Sim ──────────▶ Modbus Adapter ────────┤         │
OPC UA Sim ──────────▶ OPC UA Adapter ────────┘   ┌────┴─────┐
                                                   │ Dashboard│
                                          ┌─────── ▶ alerts   │
                                          │         │ latest   │
                                           │         │ semantic
                                           │         │ history  │
                                           │         └────┬─────┘
                                    ┌───── ▶ Fuseki (SPARQL)
                                    │
                              Semantic Write (best-effort)
```

| Layer | Directory | Runtime | Port |
|---|---|---|---|---|
| Data contract (shared) | `shared/` | Import-only | — |
| Backend API | `backend/` | FastAPI + SQLite, 6 endpoints + rules engine | 8000 |
| Connectivity | `connectivity/` | MQTT adapter → HTTP forward | — |
| Mock generator | `analytics/mock/` | CLI tool | — |
| Semantic layer | `semantic-layer/` | RDF mapping + Fuseki write path | — |
| Knowledge graph | `deploy/fuseki/` | Apache Jena Fuseki, SPARQL endpoint | 3030 |
| Dashboard | `dashboard/` | Vue 3 + Vite + ECharts, 8 components | 5173 |
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

### 2. Run tests (69 Python + 9 dashboard = 78 tests, ~15 seconds)

```bash
pytest shared/tests/ backend/tests/ connectivity/tests/ analytics/tests/ semantic-layer/tests/ -v
cd dashboard && npx vitest run && cd ..
```

### 3. Start the full stack (Docker)

```bash
docker compose -f deploy/docker-compose.yml up -d
```

This starts Mosquitto (1883), Backend (8000), Dashboard (5173), Fuseki (3030), 4 protocol adapters, and 3 simulators. All simulators auto-push data; no manual mock needed.

### 4. Push mock data

```bash
python -m analytics.mock.generator --count 5
```

### 5. Verify

```bash
curl http://localhost:8000/health                    # → {"status":"ok"}
curl http://localhost:8000/api/v1/devices            # → ["sensor_dht22_01", ...]
curl "http://localhost:8000/api/v1/latest"           # → 5 devices with aggregated measurements
curl "http://localhost:8000/api/v1/history?limit=5"  # → {"items":[...], "total":...}
curl "http://localhost:8000/api/v1/alerts?limit=10"  # → {"items":[...], "total":...}
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

## Modbus TCP Adapter

The Modbus adapter connects to a Modbus TCP server via `MODBUS_HOST` (default `localhost`) and `MODBUS_PORT` (default `1502`). It polls holding registers at `MODBUS_POLL_INTERVAL` (default `2s`) and maps raw register values to `UnifiedMessage`.

| Register (zero-based) | Measurement.type | Unit |
|---|---|---|
| `holding[0]` | `smoke` | `ppm` |
| `holding[1]` | `co` | `ppm` |
| `holding[2]` | `combustible_gas` | `ppm` |

One poll cycle produces a single `UnifiedMessage` with all three measurements. `MODBUS_DEVICE_ID` (default `sensor_mq2_01`) is set via environment variable since registers carry no device identifier.

```
python -m connectivity.runner --adapter modbus
```

Modbus simulator (`analytics/src/analytics/mock/modbus_server.py`): serves holding registers on `MODBUS_PORT`, auto-updating values periodically.

---

## Multi-Protocol Adapters

All 5 subsystems enter through different protocols. Backend only sees `UnifiedMessage`, never protocol details. The Docker Compose stack runs all 4 adapters simultaneously:

| Subsystem | Protocol | Adapter Port | Simulator |
|---|---|---|---|
| Temp/Humidity | MQTT | — | `analytics.mock.generator --subsystem temp_humidity` |
| Lighting | REST | 8100 | `analytics.mock.rest_pusher` |
| Gas | Modbus TCP | — | `analytics.mock.modbus_server` (port 1502) |
| AGV | OPC UA | — | `analytics.mock.opcua_server` (port 4840) |
| Counting | REST | 8100 | `analytics.mock.rest_pusher` |

All adapters output `UnifiedMessage` with `schema_version="v1"` and their respective `Protocol` enum.
For protocol-specific payload formats and response codes, see each adapter's module docstring.

---

## Backend API Reference

| Method | Path | Purpose | Request Body | Response |
|---|---|---|---|---|---|
| `GET` | `/health` | Health check | — | `200 {"status":"ok"}` |
| `POST` | `/api/v1/data` | Ingest sensor data | `UnifiedMessage` | `201 {"id":"uuid"}` |
| `GET` | `/api/v1/data` | Query sensor data | Query: `device_id`, `limit` (1-1000), `since` (ISO 8601) | `200 [rows...]` |
| `GET` | `/api/v1/devices` | List known device IDs | — | `200 ["id1","id2"]` |
| `GET` | `/api/v1/latest` | Latest values per device per type | Query: `device_id` (optional) | `200 [{device_id, subsystem, measurements}]` |
| `GET` | `/api/v1/history` | Time-range query with pagination | Query: `device_id`, `since`, `until`, `limit`, `offset` | `200 {"items":[...], "total":N}` |
| `GET` | `/api/v1/alerts` | Recent alerts with filtering | Query: `device_id`, `level` (warning\|critical), `limit`, `offset` | `200 {"items":[...], "total":N}` |
| `POST` | `/api/v1/control` | Issue control command | `{"device_id":str,"action":str,"params":{}}` | `202 {"command_id":"uuid"}` |
| `GET` | `/api/v1/control/{id}` | Check command status | — | `200 {"status":"pending"}` |
| `GET` | `/api/v1/semantic` | SPARQL-backed semantic views | Query: `view` (sensor-observations\|co-temp-sensors) | `200 {"results":[...]}` |

---

## Console Shell

The dashboard is organised as a 4-tab console:

| Tab | View | Purpose |
|---|---|---|
| 监控 | `DashboardView` | Real-time monitoring (5 subsystem panels + alerts + semantics) |
| 调试 | `ApiConsoleView` | Manual API debugging — 8 endpoints with parameter editors and POST templates |
| 设备 | `DeviceManagerView` | Device inventory table, online inference, detail drawer with control placeholders |
| 系统 | `SystemStatusView` | Health probes, throughput rate (differential `/history` polling), event timeline |

**Refresh strategy**: monitoring data every 3s; semantic/Fuseki probes every 10s; device list every 10s. API Console is manual-only.

**StatusBar protocol lights** use `DEVICE_META` (`dashboard/deviceMeta.ts`) to map protocols to device IDs. A protocol light shows green when the device's latest timestamp is within 30s of now. Fuseki is probed via `/api/v1/semantic?view=sensor-observations`.

**`DEVICE_META`** is the single source of truth for device–protocol–subsystem–connectVia mapping on the frontend. When adding a new device or changing protocol allocation, update this file.

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

-- Alerts — populated by rules engine within the same transaction as sensor_data insert
CREATE TABLE alerts (
    id TEXT PRIMARY KEY,
    rule_name TEXT NOT NULL,           -- matches rules.py RULES
    level TEXT NOT NULL,               -- "warning" | "critical"
    device_id TEXT NOT NULL,
    subsystem TEXT NOT NULL,
    measurement_type TEXT NOT NULL,
    value REAL NOT NULL,               -- trigger value
    threshold REAL NOT NULL,           -- rule threshold
    message TEXT NOT NULL,
    source_record_id TEXT NOT NULL,    -- FK-like, links to sensor_data.id
    triggered_at TEXT NOT NULL
);
```

---

## Semantic Layer

The ontology in `semantic-layer/src/semantic_layer/ontology/` defines the **shared vocabulary** using SOSA/SSN standards:

- **6 Sensor classes**: TemperatureSensor, HumiditySensor, GasSensor, ProximitySensor, CountSensor, OccupancySensor
- **9 ObservableProperties**: measuresTemperature, measuresHumidity, measuresCO, measuresSmoke, measuresCombustibleGas, measuresDistance, measuresCount, measuresOccupancy, measuresLightState
- **5 Subsystem groupings**: TempHumiditySubsystem, LightingSubsystem, GasMonitoringSubsystem, AGVObstacleSubsystem, CountingSubsystem
- **3 Custom properties**: `belongsToSubsystem`, `hasUnit`, `transportedVia`

### Semantic Mapping (`mapping.py`)

`to_rdf_graph()` converts a `UnifiedMessage` into an `rdflib.Graph` with SOSA Observation triples. Three lookup tables map measurement types to observable properties, sensor classes, and subsystem resources. Only verified in pytest via local SPARQL queries — not wired to backend runtime.

---

## Alert Rules Engine

`backend/src/backend/rules.py` defines 5 declarative alert rules as a list of dicts. `evaluate()` is a **pure function** that takes a single `Measurement` and returns triggered alerts — it does not access the database.

Rule evaluation is invoked inside `store.insert_sensor_data()` so that sensor insertion and alert insertion happen in the same SQLite transaction. Alerts are deduplicated: the same `(rule_name, device_id)` pair will not re-fire within a 30-second window.

| Rule | Measurement | Op | Threshold | Level |
|---|---|---|---|---|
| `high_temp` | temperature | > | 38 | warning |
| `smoke_warning` | smoke | > | 8 | warning |
| `co_warning` | co | > | 35 | critical |
| `gas_leak` | combustible_gas | > | 3 | critical |
| `agv_close` | distance | < | 30 | warning |

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
├── backend/                       FastAPI + SQLite + rules
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── src/backend/
│   │   ├── main.py                App factory + lifespan + 6 routers
│   │   ├── config.py              Env-var config
│   │   ├── models.py              API request/response Pydantic models
│   │   ├── logs.py                 Structured JSON log utility
│   │   ├── rules.py               Alert rule definitions + evaluate()
│   │   ├── store.py               SQLite CRUD + alerts table + rule evaluation
│   │   └── api/                   ingest / query / control / latest / history / alerts / semantic
│   └── tests/                     34 tests
│
├── connectivity/                  Protocol adapters
│   ├── pyproject.toml             + pymodbus, asyncua, fastapi, uvicorn
│   ├── Dockerfile
│   ├── src/connectivity/
│   │   ├── runner.py              Adapter entry point (--adapter mqtt|rest|modbus|opcua|all)
│   │   ├── models.py              Config (all 4 protocol params)
│   │   ├── router.py              HTTP forwarder with retry
│   │   └── adapters/
│   │       ├── base.py            Abstract adapter ABC
│   │       ├── mqtt_adapter.py    Full MQTT implementation
│   │       ├── rest_adapter.py    Full REST implementation (FastAPI server, port 8100)
│   │       ├── modbus_adapter.py  Full Modbus implementation (polling)
│   │       └── opcua_adapter.py   Full OPC UA implementation (subscription)
│   └── tests/                     27 tests (mqtt 9 + router 6 + rest 6 + modbus 4 + opcua 2)
│
├── analytics/                     Mock data & future analysis
│   ├── pyproject.toml             + pymodbus, asyncua, httpx
│   ├── src/analytics/mock/
│   │   ├── generator.py           CLI MQTT mock (--subsystem filter)
│   │   ├── rest_pusher.py         REST pusher, POSTs lighting + counting payloads
│   │   ├── modbus_server.py       Modbus TCP simulator, periodic register updates
│   │   └── opcua_server.py        OPC UA simulator, periodic node value updates
│   └── tests/                     23 tests (generator 8 + rest_pusher 2 + modbus_server 11 + opcua_server 2)
│
├── semantic-layer/                Shared vocabulary + RDF mapping + Fuseki write
│   ├── pyproject.toml             + httpx
│   ├── aas/                       AAS v3-aligned descriptors (5 subsystems + index)
│   ├── src/semantic_layer/
│   │   ├── mapping.py             UnifiedMessage → SOSA Observation triples
│   │   ├── fuseki.py              to_turtle() + write_to_fuseki()
│   │   └── ontology/
│   │       └── smart-factory.ttl  Turtle file (SOSA/SSN + custom properties)
│   └── tests/                     21 tests (ontology 6 + mapping 5 + fuseki 5 + aas 5)
│
├── dashboard/                     Vue 3 + ECharts console
│   ├── package.json
│   ├── vite.config.ts             Proxy /api,/health → backend:8000
│   ├── index.html
│   ├── deviceMeta.ts              Device protocol/subsystem/connectVia map
│   └── src/
│       ├── main.ts                Vue app bootstrap
│       ├── App.vue                Tab shell: 监控 | 调试 | 设备 | 系统
│       ├── api.ts                 Typed fetch wrappers + rawRequest
│       ├── layouts/
│       │   └── ConsoleLayout.vue  Header tabs + footer StatusBar + slot
│       ├── views/
│       │   ├── DashboardView.vue  Monitor: 5 charts + alerts + semantics
│       │   ├── ApiConsoleView.vue Debug: 8-endpoint manual HTTP panel
│       │   ├── DeviceManagerView.vue  Devices: table + detail drawer
│       │   └── SystemStatusView.vue   System: health, throughput, events
│       └── components/
│           ├── DeviceCard.vue       Unified panel card (protocol badge + @open)
│           ├── MiniChart.vue        Compact area line per measurement in drawer
│           ├── StatusBar.vue      5 protocol lights + counters (3s/10s)
│           ├── DeviceDrawer.vue   Reusable right-slide detail panel (+ chart toggle)
│           ├── JsonViewer.vue     Formatted JSON display
│           ├── TempGauge.vue ...  (5 chart components)
│           ├── AlertsPanel.vue | HistoryTable.vue | SemanticPanel.vue
│   └── tests/                     18 tests (vitest)
│
├── deploy/                        Infrastructure
│   ├── docker-compose.yml         mosquitto + backend + dashboard + fuseki + 4 adapters + 3 simulators
│   ├── mqtt/mosquitto.conf        Anonymous access, stdout logging
│   ├── fuseki/shiro.ini           Dev auth config, anon read/write
│   └── .env.example
│
├── docs/                           Demo script, port diagram, poster copy
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
- [x] Alert rules engine evaluates inline, 5 rules with 30s dedup
- [x] `/latest` aggregates per-device per-type newest values
- [x] `/history` supports time-range query with pagination
- [x] `/alerts` supports filtering by device_id and level
- [x] REST adapter: FastAPI server (port 8100), lighting + counting payload parsing, 202/400/502 semantics
- [x] Modbus TCP adapter: polling registers, parse_registers() pure function, pymodbus 3.6–3.12
- [x] OPC UA adapter: subscription to distance node, async queue → forward pattern
- [x] REST pusher: periodic lighting + counting POSTs, retry on connection refused
- [x] Modbus simulator: periodic register updates, 3.x/4.x compatibility
- [x] OPC UA simulator: periodic node value updates
- [x] Runner: --adapter mqtt|rest|modbus|opcua|all
- [x] Docker Compose: 4 protocols + 3 simulators + Fuseki running simultaneously
- [x] Port registry: 1502 (Modbus), 4840 (OPC UA), 8100 (REST), 3030 (Fuseki)
- [x] Semantic runtime: Fuseki SPARQL endpoint, best-effort write via BackgroundTasks
- [x] `/api/v1/semantic`: sensor-observations + co-temp-sensors whitelist views
- [x] Dashboard semantic panel: sensor catalogue table
- [x] AAS descriptors: 5 v3-aligned JSON files + index, semantic URIs align with TTL
- [x] Dashboard: responsive 3/2/1-column grid, skeleton loaders, error fallback
- [x] Demo docs: demo-script.md, port-diagram.md, poster-copy.md
- [x] Console shell: 4-tab navigation (monitor/debug/devices/system), 3s/10s differential refresh
- [x] API Console: 8-endpoint manual HTTP panel, POST templates, status/time/response
- [x] StatusBar: 5 protocol lights (30s freshness), device/alert counters
- [x] Device Manager: table + detail drawer with control placeholder
- [x] System Status: health probes, throughput rate, event timeline
- [x] DeviceCard: unified panel component with protocol badge, reusable across views
- [x] Drawer charts: MiniChart per measurement type in device drawer, JSON/chart toggle
- [ ] Real hardware integration (future)
- [ ] InfluxDB / IoTDB migration (future)
- [ ] BaSyx AAS runtime (future)
- [ ] Real device control actuation (future)
