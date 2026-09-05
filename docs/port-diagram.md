# Data and control paths

| Origin | Destination | Endpoint |
|---|---|---|
| DHT22 | MQTT broker | Configured broker, normally TCP 1883 |
| MQTT adapter | Backend | POST /ingest/api/v1/data |
| PIR/counting firmware | REST adapter or backend | POST /adapter/rest/ingest or /ingest/api/v1/data, with API key |
| Gas adapter | Gas hardware | Configured Modbus TCP endpoint and register map |
| AGV sensor | Serial gateway | Configured serial device |
| OPC UA adapter | Serial gateway | Configured OPC UA endpoint and certificates |
| Dashboard | Backend | Same-origin reverse proxy |
| Backend | MQTT receiver | factory/{subsystem}/control/{device_id} |
| Physical receiver | Backend | POST /api/v1/control/{command_id}/ack |

Docker exposes the backend on loopback by default. Set BACKEND_BIND_ADDRESS and the reachable PUBLIC_BACKEND_URL/HOST_LAN_IP when hardware posts directly. Restrict access on the test network. Fuseki stays inside the container network.
