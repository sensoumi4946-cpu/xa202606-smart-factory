# Validation and Evidence

The `validation/` directory contains configuration checks, live-smoke tools, benchmark helpers and evidence protocols.

## Principle

Only reproducible evidence may be used for acceptance claims.

- synthetic sample JSON can verify contracts and demo logic;
- synthetic data must not be presented as sensor accuracy;
- unit tests must not be presented as physical E2E verification;
- simulator ACKs must not be presented as real actuator execution;
- short-duration observations must not be extrapolated to 24/48 h production stability.

## Useful commands

```bash
python validation/run_validation.py
python validation/run_benchmark.py
python validation/live_smoke.py
python validation/measure_ingest_performance.py
python scripts/validate_sample_data.py
```

Read:

```text
validation/EVIDENCE_PROTOCOL.md
```

before collecting evidence.

## Competition test status

The retained final test report documents a 4-hour system observation with 1440 process samples and zero failures on the monitored HTTP checks. Resource stability remains partial because RSS increased during the window and long-tail latency was observed.
