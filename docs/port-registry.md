# Port Registry

This file is the single registry for local development and Docker Compose ports. Add new services here before assigning ports in code, `.env.example`, or Compose files.

## Active Ports

| Port | Service | Directory | Protocol | Status | Notes |
|---:|---|---|---|---|---|
| 1883 | Mosquitto MQTT broker | `deploy/` | MQTT | Active | Mock generator publishes here; connectivity subscribes here |
| 1502 | Modbus simulator | `deploy/` | Modbus | Active | Mock Modbus TCP server; connectivity-modbus polls here |
| 4840 | OPC UA simulator | `deploy/` | OPC UA | Active | Mock OPC UA server; connectivity-opcua subscribes here |
| 5173 | Dashboard dev server | `dashboard/` | HTTP | Active | Vite dev server |
| 8000 | Backend API | `backend/` | HTTP | Active | FastAPI, `/health`, `/api/v1/*` |
| 8100 | REST adapter | `connectivity/` | HTTP | Active | FastAPI server; rest-pusher POSTs vendor payloads here |
| 3030 | Apache Jena Fuseki | `deploy/` | HTTP/SPARQL | Active | Knowledge graph; backend writes triples and runs SPARQL views |

## Reserved Future Ports

| Port | Service | Directory | Protocol | Status | Notes |
|---:|---|---|---|---|---|
| 8086 | InfluxDB | `deploy/` | HTTP | Reserved | Candidate time-series database for future migration |
| 8081 | Eclipse BaSyx | `semantic-layer/` | HTTP | Reserved | Candidate AAS runtime endpoint |

## Rules

- Do not reuse a port for another service.
- Prefer standard default ports unless they conflict with existing assignments.
- If a service exposes multiple ports, document all externally reachable ports here.
- Internal-only container ports do not need host exposure unless used by developers or tests.
