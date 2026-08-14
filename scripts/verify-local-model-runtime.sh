#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$REPO_DIR/docker-compose.yml"
BASE_URL="http://localhost:${FOUNDRY_PORT:-8000}"
TIMEOUT_SECONDS="${FOUNDRY_STARTUP_TIMEOUT:-120}"

cleanup() {
  docker compose -f "$COMPOSE_FILE" down local-model-runtime >/dev/null 2>&1 || true
}
trap cleanup EXIT

printf 'Starting local model runtime...\n'
docker compose -f "$COMPOSE_FILE" up -d --build local-model-runtime

printf 'Waiting for %s/healthz...\n' "$BASE_URL"
for ((attempt = 1; attempt <= TIMEOUT_SECONDS; attempt++)); do
  if health_payload="$(curl --silent --fail "$BASE_URL/healthz" 2>/dev/null)"; then
    printf '%s\n' "$health_payload"
    break
  fi
  if (( attempt == TIMEOUT_SECONDS )); then
    echo "Local model runtime did not become ready" >&2
    docker compose -f "$COMPOSE_FILE" logs --no-color local-model-runtime >&2 || true
    exit 1
  fi
  sleep 1
done

models_payload="$(curl --silent --fail "$BASE_URL/v1/models")"
printf '%s\n' "$models_payload"
MODELS_PAYLOAD="$models_payload" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["MODELS_PAYLOAD"])
models = {item["id"]: item for item in payload.get("data", [])}
required = {"yolo", "florence-2", "phi-4-multimodal"}
missing = required - models.keys()
unavailable = [model_id for model_id in required if not models[model_id].get("available")]
if missing:
    raise SystemExit(f"Missing models: {', '.join(sorted(missing))}")
if unavailable:
    raise SystemExit(f"Unavailable models: {', '.join(sorted(unavailable))}")
print("Local model runtime availability check passed")
PY
