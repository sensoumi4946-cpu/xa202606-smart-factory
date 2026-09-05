#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SOURCE_DIR=$(cd -- "$SCRIPT_DIR/../.." && pwd)
APP_DIR=/opt/xa202606
CONFIG_DIR=/etc/xa202606
SYSTEMD_DIR=/usr/lib/systemd/system
START_SERVICES=false
WHEELHOUSE=

usage() {
  echo "Usage: sudo $0 [--start] [--wheelhouse DIR]"
}

while (($#)); do
  case "$1" in
    --start) START_SERVICES=true ;;
    --wheelhouse)
      shift
      WHEELHOUSE=${1:?--wheelhouse requires a directory}
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this installer as root." >&2
  exit 1
fi

source /etc/os-release
if [[ ${ID,,} != "openeuler" ]]; then
  echo "Unsupported operating system: ${ID:-unknown}; this installer targets openEuler." >&2
  exit 1
fi

dnf install -y python3 python3-pip python3-devel gcc openssl-devel libffi-devel curl

if ! getent group xa202606 >/dev/null; then
  groupadd --system xa202606
fi
if ! id xa202606 >/dev/null 2>&1; then
  useradd --system --gid xa202606 --home-dir "$APP_DIR" --shell /sbin/nologin xa202606
fi
if getent group dialout >/dev/null; then
  usermod -a -G dialout xa202606
fi

install -d -m 0755 "$APP_DIR"
install -d -m 0750 -o xa202606 -g xa202606 /var/lib/xa202606 /run/xa202606
install -d -m 0750 -o root -g xa202606 "$CONFIG_DIR" "$CONFIG_DIR/certificates"

python3 -m venv "$APP_DIR/venv"
PIP_ARGS=(--disable-pip-version-check)
if [[ -n "$WHEELHOUSE" ]]; then
  WHEELHOUSE=$(cd -- "$WHEELHOUSE" && pwd)
  PIP_ARGS+=(--no-index --find-links "$WHEELHOUSE")
fi
"$APP_DIR/venv/bin/python" -m pip install "${PIP_ARGS[@]}" --upgrade pip
"$APP_DIR/venv/bin/python" -m pip install "${PIP_ARGS[@]}" \
  "$SOURCE_DIR/shared" \
  "$SOURCE_DIR/semantic-layer" \
  "$SOURCE_DIR/analytics" \
  "$SOURCE_DIR/backend" \
  "$SOURCE_DIR/connectivity"

install -m 0644 "$SOURCE_DIR/bindings.ttl" "$CONFIG_DIR/bindings.ttl"
install -m 0644 "$SOURCE_DIR/thresholds.ttl" "$CONFIG_DIR/thresholds.ttl"
for example in backend connectivity; do
  target="$CONFIG_DIR/$example.env"
  if [[ ! -e "$target" ]]; then
    install -m 0640 -o root -g xa202606 \
      "$SCRIPT_DIR/$example.env.example" "$target"
  fi
done

for cert in client-cert.pem client-key.pem server-cert.pem server-key.pem; do
  if [[ -f "$SCRIPT_DIR/certificates/$cert" ]]; then
    install -m 0640 -o root -g xa202606 \
      "$SCRIPT_DIR/certificates/$cert" "$CONFIG_DIR/certificates/$cert"
  fi
done

install -m 0644 "$SOURCE_DIR/deploy/systemd/xa202606-backend.service" "$SYSTEMD_DIR/"
install -m 0644 "$SOURCE_DIR/deploy/systemd/xa202606-bindingd.service" "$SYSTEMD_DIR/"
install -m 0644 "$SOURCE_DIR/deploy/systemd/xa202606-connectivity@.service" "$SYSTEMD_DIR/"
install -m 0644 "$SOURCE_DIR/deploy/systemd/xa202606-opcua-gateway.service" "$SYSTEMD_DIR/"
install -m 0750 -o root -g xa202606 \
  "$SOURCE_DIR/deploy/openeuler/reload-bindings.sh" \
  /usr/local/sbin/xa202606-reload
systemctl daemon-reload

echo "Installed XA-202606 on openEuler. Review $CONFIG_DIR/*.env before starting."
if $START_SERVICES; then
  if grep -Rqs 'CHANGE_ME' "$CONFIG_DIR"/*.env; then
    echo "Refusing --start: replace all CHANGE_ME values in $CONFIG_DIR/*.env." >&2
    exit 1
  fi
  systemctl enable --now xa202606-bindingd.service xa202606-backend.service
  systemctl enable --now \
    xa202606-connectivity@mqtt.service \
    xa202606-connectivity@rest.service
  echo "MQTT and REST adapters started. Enable Modbus/OPC UA after configuring endpoints."
fi
