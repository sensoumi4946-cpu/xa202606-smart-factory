# Analytics

The analytics package implements interpretable prediction, anomaly/context analysis, hazard reasoning, safety-control logic and decision provenance.

## Main components

- `FaultPredictor`
- `TrendForecaster`
- `ThresholdResolver`
- `AnomalyDetector`
- `CrossSubsystemCorrelator`
- `HazardReasoner`
- `SafetyController`
- `PolicyVerifier`
- `DecisionProvenance`
- `AgvGuard`

## Prediction vs. hazard boundary

The current master intentionally separates forecasting from already-breached safety states:

```text
current value not breached
        ↓
FaultPredictor
        ↓
threshold-crossing estimate

current value already breached
        ↓
HazardReasoner / direct safety logic
```

An already-breached value is not returned as a zero-second forecast.

`FaultPredictor` is an interpretable trend/threshold-crossing model. It is **not** a supervised fault-probability classifier and must not be presented with unsupported classification accuracy.

## Hazard reasoning

Hazard rules combine evidence across measurements/subsystems within a bounded time window.

Current code defaults include:

- hazard correlation window: 20 s
- hazard cooldown: 30 s
- SafetyController minimum action interval: 20 s
- automatic clear hold: 120 s

## Decision provenance

Safety decisions retain structured evidence and can be linked to the audit chain. Repeated active conditions can be counted without issuing a duplicate command each time.

## Formal policy verification

`PolicyVerifier` is for policy/conflict verification, not the hot ingest path.

## Test

```bash
python -m pytest analytics/tests -q
```
