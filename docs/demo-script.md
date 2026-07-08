# Demo Script

A step-by-step defence walkthrough. Run the full stack first:

```bash
docker compose -f deploy/docker-compose.yml up -d
```

## Steps

| # | Step | Time | Action | Narration |
|---|---|---|---|---|
| 1 | Boot | 30s | `docker compose ps` | Docker Compose orchestrates MQTT broker, four protocol adapters, backend, Fuseki knowledge graph, and dashboard — all self-contained, no real hardware needed. |
| 2 | Protocol heterogeneity | 60s | Show adapter logs for mqtt, rest, modbus, opcua | Five subsystems enter through four protocols: MQTT (temperature), REST (lighting & counting), Modbus (gas), OPC UA (AGV). Every adapter normalises to the same `UnifiedMessage` contract and posts to the backend. |
| 3 | Semantic normalisation | 60s | `curl localhost:8000/api/v1/semantic?view=sensor-observations` | Backend maps each reading to an SOSA Observation triple and writes to Fuseki. This single SPARQL view links sensors, subsystems, observed properties, and protocols — heterogeneous devices now speak the same vocabulary. The dashboard semantic panel renders the same table in real time. |
| 4 | Alerts | 45s | `curl "localhost:8000/api/v1/alerts?limit=5"` | Rule engine evaluates thresholds inline. Critical alerts blink red on the dashboard. Combined gas + temperature rules demonstrate cross-device correlation. |
| 5 | AAS descriptors | 30s | `ls semantic-layer/aas/ && cat semantic-layer/aas/aas_index.json` | Five AAS descriptors, one per subsystem, with asset information, submodels, observed properties, and semantic URIs. Digital-twin descriptor-ready. |
| 6 | Wrap-up | 15s | Return to dashboard | Deployable on UOS / openEuler / HongZOS. Heterogeneous devices, unified semantics, real-time alerts, digital-twin ready. |

## Troubleshooting

- Dashboard blank: wait 5-10s for simulator data to flow, or refresh.
- Single panel failing: other panels continue — graceful degradation.
- Fuseki unreachable: semantic panel shows "service unavailable", monitoring panels unaffected.
