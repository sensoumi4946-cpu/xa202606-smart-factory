# Poster Copy — XA-202606 Smart Factory Platform

Ready-to-typeset copy for the architecture poster. Titles are bilingual;
the three core blurbs map to the platform's three differentiators.

---

## Titles

- **中文**：智慧工厂安全监控与控制平台
- **English**: Smart Factory Safety Monitoring & Control Platform
- **副标题 / Subtitle**：面向国产操作系统的语义互操作物联网平台 ·
  A Semantic-Interoperability IoT Platform for Domestic Operating Systems
- **Topic**: XA-202606 · "挑战杯" 揭榜挂帅擂台赛 · ArcherMind Technology

---

## Core blurbs

### 1. 协议归一化 · Protocol Normalisation

五个安全子系统、四种工业协议（MQTT / Modbus / OPC UA / REST），
全部归一化为同一套 `UnifiedMessage` 数据契约。异构设备接入不再需要
点对点适配，新增设备只需实现一个适配器。

> Five safety subsystems over four industrial protocols, all normalised
> into a single `UnifiedMessage` contract — heterogeneity handled once,
> at the edge.

### 2. 语义互操作 · Semantic Interoperability

基于 SOSA/SSN 本体与 Apache Jena Fuseki 知识图谱，每条读数被映射为
标准化的 Observation 三元组。设备"按含义"而非"按格式"对话，支持跨设备
语义关联（如危气 + 温度 → 火情预警）。

> A shared SOSA/SSN ontology plus an Apache Jena Fuseki knowledge graph
> let devices speak by meaning, not by raw format — enabling cross-device
> correlation such as gas + temperature → fire risk.

### 3. AAS 数字孪生 · AAS Digital Twin

五份贴近 AAS v3 结构的资产管理壳描述文件，涵盖资产信息、子模型、
观测属性与语义 URI。数字孪生 descriptor-ready，可无缝对接 Eclipse BaSyx。

> Five AAS v3-aligned Asset Administration Shell descriptors —
> digital-twin descriptor-ready, drop-in for an Eclipse BaSyx runtime.

---

## Technology stack icons

| Layer | Tools |
|---|---|
| Domestic OS | 统信 UOS · openEuler · HongZOS |
| Edge / MCU | ESP32 · Raspberry Pi · Arduino |
| Sensors | DHT22 · PIR · MQ-2/MQ-7 · HC-SR04 · IR break-beam |
| Protocols | MQTT · Modbus · OPC UA · HTTP/REST |
| Semantics | Eclipse BaSyx · Apache Jena · SAREF4INMA / SOSA-SSN |
| Storage | SQLite · InfluxDB / IoTDB (roadmap) · 达梦 / KingbaseES |
| Analytics | Python · scikit-learn · rule engine |
| Security | TLS · auth · audit log · 国密 SM2/SM4 |
| Dashboard | Vue 3 · Apache ECharts |

---

## QR code placeholder

```
┌─────────────┐
│             │
│   [ QR ]    │   仓库地址 / Repository
│             │   扫码查看源码与演示
└─────────────┘
```

> Placeholder — replace with a QR code linking to the Gitee repository
> before printing.
