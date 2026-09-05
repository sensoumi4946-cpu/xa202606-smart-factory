# Port Registry

This file is the single registry for local development and Docker Compose ports. Add new services here before assigning ports in code, `.env.example`, or Compose files.

## Active Ports

| Port | Service | Directory | Protocol | Status | Notes |
|---:|---|---|---|---|---|
| 1883 | Mosquitto MQTT broker | `deploy/` | MQTT | Active | Physical sensors publish; connectivity subscribes |
| 1502 | External Modbus endpoint | hardware | Modbus | Optional | Configure `MODBUS_HOST`; no simulator is committed |
| 4840 | HC-SR04 serial gateway or external endpoint | `connectivity/` / hardware | OPC UA | Optional | Configure `OPCUA_ENDPOINT`; openEuler gateway is `sf-opcua-serial-gateway` |
| 5173 | Dashboard dev server | `dashboard/` | HTTP | Active | Vite dev server |
| 8000 | Backend API | `backend/` | HTTP | Active | FastAPI, `/health`, `/api/v1/*` |
| 8100 | REST adapter | `connectivity/` | HTTP | Active | FastAPI server; Authenticated vendor or unified observations |
| 3030 | Apache Jena Fuseki | `deploy/` | HTTP/SPARQL | Internal | Knowledge graph; backend writes triples and runs SPARQL views |

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
