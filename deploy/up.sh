set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE="deploy/.env"

gen() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }

if [ ! -f "$ENV_FILE" ]; then
  echo "==> generating $ENV_FILE"
  LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "backend")
  cat > "$ENV_FILE" <<EOF
API_KEY=$(gen)
FUSEKI_ADMIN_PASSWORD=$(gen)
COMMAND_SIGNING_KEY=$(gen)
HOST_LAN_IP=${LAN_IP}
HARDWARE_PROFILE=mock
LLM_API_KEY=
LLM_MODEL=qwen-plus
EOF
  echo "    secrets written; keep this file out of git"
fi

echo "==> building and starting"
docker compose --env-file "$ENV_FILE" -f deploy/docker-compose.yml up -d --build

echo "==> waiting for backend"
for i in $(seq 1 60); do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then break; fi
  sleep 2
done

echo
docker compose --env-file "$ENV_FILE" -f deploy/docker-compose.yml ps
echo
echo "  dashboard   http://localhost:5173"
echo "  wallboard   http://localhost:5173/?wall=1"
echo "  api docs    http://localhost:8000/docs"
echo "  metrics     http://localhost:8000/metrics"
echo "  fuseki      http://localhost:3030"
echo
echo "  stop with:  docker compose --env-file $ENV_FILE -f deploy/docker-compose.yml down"
