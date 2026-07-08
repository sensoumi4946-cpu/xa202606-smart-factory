# Demo Script — XA-202606 Smart Factory Platform

A 3–5 minute defence walkthrough. Each step is designed to complete in
30–60 seconds without stalling. Run the whole stack first with
`docker compose -f deploy/docker-compose.yml up -d` and wait for the
dashboard at http://localhost:5173 to render.

---

## One-line pitch

> 一个可部署在国产操作系统上的智慧工厂安全监控平台：五个子系统、四种工业协议，
> 通过语义互操作层归一化为同一套词汇，实现跨设备关联与远程控制。

---

## Timeline

| # | Step | Time | Action | Key narration |
|---|---|---|---|---|
| 1 | Boot | 30s | `docker compose up -d` | "10+ 服务一键拉起，无需真实硬件" |
| 2 | Heterogeneity | 60s | Show 4 adapter logs | "5 个子系统，4 种协议，同一 UnifiedMessage" |
| 3 | Semantics | 60s | `GET /api/v1/semantic` + 语义面板 | "Fuseki 知识图谱 + SOSA/SSN 本体" |
| 4 | Alerts | 45s | 大屏红色闪烁告警 + `/api/v1/alerts` | "规则引擎 + 跨设备关联" |
| 5 | AAS ready | 30s | Show `semantic-layer/aas/` | "5 份 AAS 描述文件，数字孪生 ready" |
| 6 | Wrap-up | 15s | 回到大屏全景 | "国产 OS 可部署的智慧工厂安全监控平台" |

---

## Step details

### 1. Boot (30s)

```bash
docker compose -f deploy/docker-compose.yml up -d
docker compose -f deploy/docker-compose.yml ps
```

Say: 全部服务由 Compose 编排，MQTT broker、四个协议适配器、后端、
Fuseki 知识图谱、大屏一次拉起。打开 http://localhost:5173。

### 2. Protocol heterogeneity (60s)

```bash
docker compose -f deploy/docker-compose.yml logs --tail 5 connectivity-mqtt
docker compose -f deploy/docker-compose.yml logs --tail 5 connectivity-rest
docker compose -f deploy/docker-compose.yml logs --tail 5 connectivity-modbus
docker compose -f deploy/docker-compose.yml logs --tail 5 connectivity-opcua
```

Say: 温湿度走 MQTT，照明与计数走 REST，危气走 Modbus，AGV 走 OPC UA。
四条不同协议链路，全部归一化为同一个 `UnifiedMessage` 后写入后端。

### 3. Semantic normalisation (60s)

```bash
curl http://localhost:8000/api/v1/semantic?view=sensor-observations
```

Say: 后端把每条读数映射为 SOSA Observation 三元组写入 Fuseki。
这个视图用一条 SPARQL 查询把传感器、子系统、观测属性、协议关联起来 —
异构设备现在"说同一种语言"。大屏底部的语义面板实时展示这张关联表。

### 4. Alert linkage (45s)

```bash
curl "http://localhost:8000/api/v1/alerts?limit=5"
```

Say: 规则引擎对阈值越界实时告警，大屏告警面板上 critical 级别红色闪烁。
危气 + 温度可组合成火情关联规则，体现跨设备语义关联的价值。

### 5. AAS digital-twin readiness (30s)

```bash
ls semantic-layer/aas/
cat semantic-layer/aas/aas_index.json
```

Say: 五个子系统各有一份 AAS 描述文件，贴近 AAS v3 结构，
包含资产信息、子模型、观测属性与语义 URI。数字孪生 descriptor-ready，
后续可直接接入 BaSyx runtime。

### 6. Wrap-up (15s)

Say: 从异构接入到语义归一，从实时告警到数字孪生，全部可部署在
统信 UOS / openEuler 等国产操作系统上。这就是我们的智慧工厂安全监控平台。

---

## Fallback tips

- 大屏空白：等待 5–10s 让 mock 数据流入，或刷新页面。
- 某个面板加载失败：其它面板不受影响，说明降级设计已生效。
- Fuseki 未就绪：语义面板显示"语义服务不可用"，其它监控照常刷新。
