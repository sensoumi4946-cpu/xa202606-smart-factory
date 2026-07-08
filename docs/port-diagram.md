# Port Topology

Communication flow across the Docker Compose stack. Port assignments are registered in `docs/port-registry.md`.

## Data flow

```
simulators ──(native protocol)──▶ adapters ──(POST /api/v1/data)──▶ backend
                                                                       │
                                                             ┌─ SQLite
                                                             └─ Fuseki (SPARQL)

dashboard ──(REST /api/v1/*)──▶ backend
```

## Service communication

| From | To | Protocol | Direction |
|---|---|---|---|
| mosquitto | connectivity-mqtt | MQTT (sub) | Sim → Adapter |
| modbus-sim | connectivity-modbus | Modbus TCP (poll) | Sim → Adapter |
| opcua-sim | connectivity-opcua | OPC UA (sub) | Sim → Adapter |
| rest-pusher | connectivity-rest | HTTP POST | Sim → Adapter |
| connectivity-* | backend | HTTP POST /api/v1/data | Adapter → Core |
| backend | fuseki | HTTP SPARQL | Core → Knowledge |
| dashboard | backend | HTTP REST /api/v1/* | UI → Core |

## Externally exposed ports

| Port | Service |
|---:|---|
| 1883 | mosquitto |
| 1502 | modbus-sim |
| 4840 | opcua-sim |
| 8100 | connectivity-rest |
| 8000 | backend |
| 3030 | fuseki |
| 5173 | dashboard |
