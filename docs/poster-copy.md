# Poster Copy

Text for the XA-202606 architecture poster. Bilingual.

## Headline

**智慧工厂安全监控与控制平台**
*Smart Factory Safety Monitoring & Control Platform*

Built on a domestic operating system.
基于国产操作系统。

Topic XA-202606 · 挑战杯揭榜挂帅擂台赛 · ArcherMind Technology (诚迈科技)

---

## Three pillars

### Protocol Normalisation

Five safety subsystems enter through four industrial protocols —
MQTT (temperature), REST (lighting & counting), Modbus TCP (gas),
OPC UA (AGV). Each adapter outputs a single `UnifiedMessage`
contract; the backend never sees protocol differences.

### Semantic Interoperability

A shared SOSA/SSN ontology plus Apache Jena Fuseki map every
reading into a standardised Observation triple. Devices are
queried by meaning (SPARQL), not by raw format. Cross-device
correlation — e.g. gas concentration + temperature rise →
fire risk — is a query, not custom code.

### AAS Digital Twin

Five AAS v3-aligned descriptors with asset information,
submodels, observed properties, and semantic URIs.
Descriptor-ready for Eclipse BaSyx runtime.

---

## Technology Stack

| Concern | Tools |
|---|---|
| OS target | 统信 UOS / openEuler / HongZOS |
| Firmware | ESP32 / Raspberry Pi / Arduino (DHT22, PIR, MQ-2/7, HC-SR04, IR) |
| Protocols | MQTT, Modbus, OPC UA, HTTP/REST |
| Semantics | Apache Jena Fuseki, SOSA/SSN, RDFlib |
| AAS | Asset Administration Shell (descriptor-ready) |
| Backend | FastAPI + SQLite + rule engine |
| Dashboard | Vue 3 + Apache ECharts |
| Operations | Docker Compose, JSON Lines logging |

---

## Repository

gitee.com/sensoumi/xa202606-smart-factory
[ QR code placeholder ]
