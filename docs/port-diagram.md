# Port Topology

Port mappings and communication direction across the Docker Compose
stack. Canonical port assignments live in `port-registry.md`; this file
shows how the services wire together.

## Mermaid

```mermaid
flowchart LR
  subgraph sim["Simulators (analytics/)"]
    modbusSim["modbus-sim<br/>:1502"]
    opcuaSim["opcua-sim<br/>:4840"]
    restPush["rest-pusher"]
  end

  subgraph broker["Broker"]
    mosq["mosquitto<br/>:1883"]
  end

  subgraph adapters["Connectivity adapters"]
    cMqtt["connectivity-mqtt"]
    cRest["connectivity-rest<br/>:8100"]
    cModbus["connectivity-modbus"]
    cOpcua["connectivity-opcua"]
  end

  backend["backend<br/>:8000"]
  fuseki["fuseki<br/>:3030"]
  dash["dashboard<br/>:5173"]

  mosq -->|MQTT sub| cMqtt
  modbusSim -->|Modbus poll| cModbus
  opcuaSim -->|OPC UA sub| cOpcua
  restPush -->|HTTP POST| cRest

  cMqtt -->|UnifiedMessage| backend
  cRest -->|UnifiedMessage| backend
  cModbus -->|UnifiedMessage| backend
  cOpcua -->|UnifiedMessage| backend

  backend -->|SPARQL write/query| fuseki
  dash -->|REST /api/v1/*| backend
```

## ASCII fallback

```
 Simulators                 Adapters                 Core
 ----------                 --------                 ----
 modbus-sim :1502  --Modbus--> connectivity-modbus --+
 opcua-sim  :4840  --OPC UA--> connectivity-opcua  --+
 rest-pusher       --HTTP---->  connectivity-rest    +--> backend :8000
 mosquitto  :1883  --MQTT----> connectivity-mqtt   --+        |
                                                              |  SPARQL
                                                              v
                                                          fuseki :3030

 dashboard :5173  --REST /api/v1/*-->  backend :8000
```

## Externally exposed host ports

| Port | Service | Protocol |
|---:|---|---|
| 1883 | mosquitto | MQTT |
| 1502 | modbus-sim | Modbus TCP |
| 4840 | opcua-sim | OPC UA |
| 8100 | connectivity-rest | HTTP |
| 8000 | backend | HTTP / REST |
| 3030 | fuseki | HTTP / SPARQL |
| 5173 | dashboard | HTTP |

Direction summary: simulators feed adapters over their native protocol,
adapters normalise to `UnifiedMessage` and POST to the backend, the
backend persists to SQLite and writes/queries triples in Fuseki, and the
dashboard reads everything back through `/api/v1/*`.
