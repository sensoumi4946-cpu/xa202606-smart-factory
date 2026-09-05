# Physical and platform evidence protocol

The JSON files under `data/samples/` are synthetic contract fixtures. They are
not sensor accuracy, latency, stability, or openEuler qualification evidence.

## Sensor accuracy

1. Use a calibrated reference instrument whose certificate and uncertainty are recorded.
2. Collect at least 30 paired observations at low, middle, and high points of each operating range.
3. Record unrounded values in `physical_accuracy_template.csv`; do not edit failed samples.
4. Run `python validation/analyze_accuracy.py measurements.csv --output accuracy-report.json`.
5. Retain photos of the setup, instrument model/serial, calibration date, firmware hash, ambient conditions, raw CSV, and report.

Count and Boolean sensors need event confusion counts as well as numeric error:
true positives, false positives, false negatives, debounce interval, and tested event rate.

## Ingest performance

On the target openEuler machine, run:

```bash
API_KEY=... python validation/measure_ingest_performance.py \
  --requests 5000 --concurrency 16 --output ingest-openEuler.json
```

Record CPU architecture, `uname -a`, openEuler release, Python/RPM versions,
network topology, Fuseki mode, process RSS/CPU, and whether semantic writes were
enabled. A localhost synthetic result must not be presented as field-network
protocol latency.

## Stability and recovery

Run all five physical loops for at least 24 hours. Record message counts, loss,
duplicates, process restarts, maximum outage, reconnect time, disk growth, CPU,
and memory. Deliberately interrupt MQTT, Modbus, OPC UA, Fuseki, and the network,
then retain the timestamps and service logs proving recovery.

## Competition evidence boundary

Only measured artifacts are claims. Reference firmware, simulators, schemas,
screenshots, and perfectly linear example data establish implementation intent,
not physical completion or accuracy.
