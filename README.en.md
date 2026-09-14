# XA-202606 Smart Factory Safety Monitoring and Control Platform

**Team: Binding Minds**  
**Zhejiang Normal University**  
**Competition baseline: `master @ d45e5679d6cc6febc66c20e759b06375c2b6da20`**

XA-202606 integrates heterogeneous industrial devices using MQTT, REST, Modbus TCP and OPC UA, normalizes observations into `UnifiedMessage`, applies binding/contract checks and SHACL semantic gating, persists valid observations to SQLite, and then runs prediction, hazard reasoning, safety decision and audit logic.

`bindings.ttl` is the single source of truth for protocol bindings. Apache Jena Fuseki provides RDF persistence and SPARQL querying but stays outside the critical ingest path; semantic persistence failure must not stop core observation ingestion and safety analysis.

## Main pipeline

```text
Devices / protocols
        ↓
bindings.ttl / generated adapters
        ↓
UnifiedMessage
        ↓
SHACL gate
        ↓
SQLite + analytics
        ↓
FaultPredictor / HazardReasoner
        ↓
SafetyController
        ↓
backend-signed control + audit
```

## Key design points

- Binding-driven MQTT / REST / Modbus / OPC UA integration.
- A shared `UnifiedMessage` contract above all protocol adapters.
- SHACL rejects invalid observations before business persistence.
- Threshold breaches are hazards, not forecasts.
- `FaultPredictor` is an interpretable trend/threshold-crossing model, not a fault-probability classifier.
- Browser and control plane are separated: the backend signs downstream commands.
- Fuseki is optional for semantic persistence and querying and is not a prerequisite for the core ingest path.
- openEuler 24.03 LTS + systemd is the competition deployment target.

## Current device topology

| Device | Function | Subsystem | Binding |
|---|---|---|---|
| ESP32_001 | DHT22 temperature/humidity | temp_humidity | Modbus / MQTT / OPC UA |
| ESP32_002 | infrared counting | counting | REST |
| ESP32_003 | PIR + relay | lighting | REST |
| ESP32_004 | HC-SR04 AGV distance | agv | OPC UA |
| ESP32_005 | MQ-2 / MQ-7 gas sensing | gas | Modbus |

## Local setup

```bash
git clone https://github.com/sensoumi4946-cpu/xa202606-smart-factory.git
cd xa202606-smart-factory

python -m venv .venv
source .venv/bin/activate

pip install -e shared -e backend -e connectivity -e analytics -e semantic-layer
cd dashboard && npm install && cd ..
```

Required for protected backend access:

```bash
API_KEY=your_api_key
```

Required for downstream control:

```bash
COMMAND_SIGNING_KEY=your_command_signing_key
```

Start backend from the repository root:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Dashboard:

```bash
cd dashboard
npm run dev
```

## Tests

```bash
python -m pytest backend/tests connectivity/tests semantic-layer/tests analytics/tests shared/tests benchmark/tests validation/tests -q
cd firmware && python -m pytest tests -q && cd ..
cd dashboard && npm test -- --run && npm run build && cd ..
python scripts/generate_adapters.py --check
python scripts/validate_sample_data.py
python validation/run_validation.py
```

Code regression is not a substitute for field/system evidence.

## Competition evidence status

The final system test report records:

- openEuler 24.03 LTS server deployment tested;
- five device categories online in the demonstration window;
- a 4-hour continuous run;
- 1440 process samples;
- no backend PID change and zero systemd restarts;
- 1440 HTTP 200 responses each for health/latest/forecast;
- 240 HTTP 200 responses each for semantic refresh/cached queries;
- average CPU 18.38%, maximum CPU 49.39%;
- SQLite `quick_check=ok`.

The resource-stability result is still **partial** rather than a production SLA because RSS increased from about 106.22 MB to 283.85 MB during the four-hour window and long-tail latency remains visible.

## Explicit limitations

Not yet claimed as completed:

- real physical actuator closed-loop acceptance;
- production OPC UA certificate trust chain;
- traceable sensor-accuracy calibration;
- standardized 24/48-hour physical endurance testing;
- independent high-concurrency ingest benchmarking;
- unified device-side timestamps;
- supervised fault-probability classification based on a real labeled dataset.

For deployment details, see `deploy/openeuler/README.md`.
