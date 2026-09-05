#!/usr/bin/env bash
set -euo pipefail

APP_PYTHON=/opt/xa202606/venv/bin/python
CONFIG_DIR=/etc/xa202606
BACKEND_URL=${BACKEND_URL:-http://127.0.0.1:8000}

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this command as root." >&2
  exit 1
fi

if [[ -z ${API_KEY:-} && -r "$CONFIG_DIR/backend.env" ]]; then
  while IFS= read -r line; do
    if [[ $line == API_KEY=* ]]; then
      API_KEY=${line#API_KEY=}
      break
    fi
  done < "$CONFIG_DIR/backend.env"
fi
if [[ -z ${API_KEY:-} || $API_KEY == CHANGE_ME* ]]; then
  echo "A configured API_KEY is required." >&2
  exit 1
fi

"$APP_PYTHON" - <<'PY'
from pathlib import Path
from semantic_layer.meta_model import MetaModelRegistry
from semantic_layer.protocol_binding import BindingRegistry

binding_path = Path("/etc/xa202606/bindings.ttl")
threshold_path = Path("/etc/xa202606/thresholds.ttl")
bindings = BindingRegistry().load_turtle(binding_path.read_text(encoding="utf-8"))
thresholds = MetaModelRegistry().load_turtle(threshold_path.read_text(encoding="utf-8"))
if not bindings.accepted:
    raise SystemExit(f"binding validation failed: {bindings.violations}")
if not thresholds.accepted:
    raise SystemExit(f"threshold validation failed: {thresholds.violations}")
print("configuration validation passed")
PY

curl --fail --silent --show-error \
  -X POST "$BACKEND_URL/api/v1/innovation/reload" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json"
echo

systemctl reload xa202606-bindingd.service
for adapter in mqtt rest modbus opcua; do
  unit="xa202606-connectivity@$adapter.service"
  if systemctl is-active --quiet "$unit"; then
    systemctl reload "$unit"
  fi
done
echo "backend, binding service, and active adapters reloaded without process restart"
