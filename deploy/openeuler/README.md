# openEuler deployment

Supported qualification target: **openEuler 24.03 LTS, x86_64 or AArch64**.
The application requires Python 3.11; openEuler 24.03 supplies Python 3.11.

## Install

```bash
sudo bash deploy/openeuler/install.sh
sudoedit /etc/xa202606/backend.env
sudoedit /etc/xa202606/connectivity.env
sudo bash deploy/openeuler/verify.sh
sudo systemctl enable --now xa202606-bindingd.service xa202606-backend.service
sudo systemctl enable --now xa202606-connectivity@mqtt xa202606-connectivity@rest
```

Enable hardware adapters only after their endpoints and credentials have been
verified:

```bash
sudo systemctl enable --now xa202606-connectivity@modbus
sudo systemctl enable --now xa202606-connectivity@opcua
```

ESP32_004 sends HC-SR04 readings over USB/UART. Start the local OPC UA gateway
before the OPC UA client adapter:

```bash
sudo systemctl enable --now xa202606-opcua-gateway
sudo systemctl enable --now xa202606-connectivity@opcua
```

For an offline factory network, populate a wheel directory on a connected build
machine and pass it with `--wheelhouse`. It must contain application build
requirements and every transitive Python dependency.

## Reload bindings and thresholds without restarting processes

Edit `/etc/xa202606/bindings.ttl` or `/etc/xa202606/thresholds.ttl`, then run:

```bash
sudo xa202606-reload
```

The command validates both files before changing live state, reloads the
backend through its authenticated API, sends SIGHUP to `sf-bindingd`, and makes
each active adapter rebuild its binding-derived plan inside the same process.
Adding a device that uses existing measurement and unit types therefore needs
configuration reload but no process restart. Adding a new measurement or unit
type still requires extending the strict Python contract and semantic mapping.

## OPC UA security

Production OPC UA must use a site-issued client certificate, a protected private
key, and the pinned server certificate. Copy the three files described in
`certificates/README.md`, set `OPCUA_SECURITY_STRING`, then restart the instance.
Do not fall back to anonymous `None` security on a production control network.

## Qualification evidence

Running the installer elsewhere is not proof of openEuler compatibility. Save
the full output of `verify.sh`, `uname -a`, `rpm -q python3`, the service status,
and the measurement scripts under `validation/`. Test both the actual CPU
architecture and the field network used in the final demonstration.
