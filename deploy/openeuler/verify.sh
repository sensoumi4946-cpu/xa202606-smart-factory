#!/usr/bin/env bash
set -euo pipefail

source /etc/os-release
[[ ${ID,,} == "openeuler" ]] || { echo "FAIL os=${ID:-unknown}"; exit 1; }
echo "PASS os=$PRETTY_NAME"

/opt/xa202606/venv/bin/python - <<'PY'
from pathlib import Path
from semantic_layer.meta_model import MetaModelRegistry
from semantic_layer.protocol_binding import BindingRegistry

path = Path("/etc/xa202606/bindings.ttl")
registry = BindingRegistry()
result = registry.load_turtle(path.read_text(encoding="utf-8"))
if not result.accepted:
    raise SystemExit(f"FAIL bindings={result.violations}")
threshold_path = Path("/etc/xa202606/thresholds.ttl")
thresholds = MetaModelRegistry()
threshold_result = thresholds.load_turtle(threshold_path.read_text(encoding="utf-8"))
if not threshold_result.accepted:
    raise SystemExit(f"FAIL thresholds={threshold_result.violations}")
print(
    f"PASS python bindings={len(registry)} devices={len(registry.devices())} "
    f"threshold_properties={len(thresholds.properties())}"
)
PY

systemd-analyze verify \
  /usr/lib/systemd/system/xa202606-bindingd.service \
  /usr/lib/systemd/system/xa202606-backend.service \
  /usr/lib/systemd/system/xa202606-connectivity@.service \
  /usr/lib/systemd/system/xa202606-opcua-gateway.service

test -x /usr/local/sbin/xa202606-reload
echo "PASS reload command=/usr/local/sbin/xa202606-reload"

if systemctl is-active --quiet xa202606-backend.service; then
  /opt/xa202606/venv/bin/python - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5) as response:
    body = json.load(response)
if response.status != 200:
    raise SystemExit(f"FAIL backend_http={response.status}")
print(f"PASS backend={body}")
PY
else
  echo "SKIP backend health (service is not active)"
fi
