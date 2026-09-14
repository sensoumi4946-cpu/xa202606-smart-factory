# openEuler Deployment

XA-202606 uses **openEuler 24.03 LTS** as the competition target operating-system environment.

The competition deployment path uses native `systemd`; Docker Compose remains useful for development and integration.

## Services

The deployment includes systemd definitions for components such as:

- backend
- binding service
- protocol connectivity instances
- OPC UA gateway

Supporting services may also include Mosquitto and Fuseki depending on the selected profile.

## Install

From repository root:

```bash
sudo bash deploy/openeuler/install.sh
```

Then configure:

```bash
sudoedit /etc/xa202606/backend.env
sudoedit /etc/xa202606/connectivity.env
```

Verify:

```bash
sudo bash deploy/openeuler/verify.sh
```

## Required secrets

Target deployment should provide real values for:

```bash
API_KEY=...
COMMAND_SIGNING_KEY=...
```

## Reload bindings and thresholds

After a valid binding or threshold update:

```bash
sudo xa202606-reload
```

The reload path validates configuration before coordinating runtime reload.

## Ports

Typical development/demo registry:

- Backend: 8000
- Dashboard dev: 5173
- REST adapter: 8100
- MQTT: 1883
- Modbus: 1502
- OPC UA: 4840
- Fuseki: 3030

## OPC UA certificates

Production `SignAndEncrypt` operation requires valid site-specific certificates and trust configuration. Placeholder/example certificate paths are not production evidence.

See:

```text
deploy/openeuler/certificates/README.md
```

## Verified competition status

The final test report records that the platform was run on openEuler 24.03 LTS and completed a 4-hour continuous observation window with:

- 1440 process samples;
- no backend PID change;
- zero systemd restarts;
- zero failures for the monitored HTTP endpoint checks;
- CPU average 18.38%, maximum 49.39%;
- SQLite `quick_check=ok`.

This does **not** establish a 24/48-hour production SLA. RSS growth and long-tail latency remain items for follow-up.
