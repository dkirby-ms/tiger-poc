#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$REPO_DIR/docker-compose.yml"
CATALOG_FILE="$REPO_DIR/models/services.json"
TIMEOUT_SECONDS="${MODEL_SERVICE_STARTUP_TIMEOUT:-120}"

mapfile -t SERVICES < <(python3 - "$CATALOG_FILE" <<'PY'
import json
import sys

catalog = json.loads(open(sys.argv[1], encoding="utf-8").read())
for service in catalog["services"]:
    print(f"{service['model_id']}\t{service['port']}\t{service['workloadType']}\t{service['secret']}")
PY
)

cleanup() {
  docker compose -f "$COMPOSE_FILE" down >/dev/null 2>&1 || true
}
trap cleanup EXIT

printf 'Starting %d model services...\n' "${#SERVICES[@]}"
docker compose -f "$COMPOSE_FILE" up -d --build

for entry in "${SERVICES[@]}"; do
  IFS=$'\t' read -r model_id port workload secret <<<"$entry"
  base_url="http://localhost:${port}"

  printf 'Waiting for %s at %s/healthz...\n' "$model_id" "$base_url"
  for ((attempt = 1; attempt <= TIMEOUT_SECONDS; attempt++)); do
    if health_payload="$(curl --silent --fail "$base_url/healthz" 2>/dev/null)"; then
      printf '%s\n' "$health_payload"
      break
    fi
    if ((attempt == TIMEOUT_SECONDS)); then
      echo "Service $model_id did not become ready" >&2
      docker compose -f "$COMPOSE_FILE" logs --no-color >&2 || true
      exit 1
    fi
    sleep 1
  done

  models_payload="$(curl --silent --fail "$base_url/v1/models")"
  printf '%s\n' "$models_payload"
  MODEL_ID="$model_id" MODELS_PAYLOAD="$models_payload" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["MODELS_PAYLOAD"])
model_id = os.environ["MODEL_ID"]
entries = payload.get("data", [])

if len(entries) != 1:
    raise SystemExit(f"{model_id}: service must expose exactly one model, found {len(entries)}")
if entries[0]["id"] != model_id:
    raise SystemExit(f"{model_id}: service exposes '{entries[0]['id']}'")
if not entries[0].get("available"):
    raise SystemExit(f"{model_id}: model is not available")
if entries[0].get("state") != "Running":
    raise SystemExit(f"{model_id}: deployment state is '{entries[0].get('state')}'")
PY

  if [[ "$workload" == "predictive" ]]; then
    route="/v1/predict"
    body='{"image":"base64-image-data"}'
    expected_object="prediction"
  else
    route="/v1/chat/completions"
    body='{"messages":[{"role":"user","content":"Describe the image."}]}'
    expected_object="chat.completion"
  fi

  unauthorized_code="$(curl --silent --output /dev/null --write-out '%{http_code}' \
    -X POST "$base_url$route" -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer wrong-secret' --data "$body")"
  if [[ "$unauthorized_code" != "401" ]]; then
    echo "$model_id: expected 401 for a wrong credential, got $unauthorized_code" >&2
    exit 1
  fi

  inference_payload="$(curl --silent --fail -X POST "$base_url$route" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $secret" \
    --data "$body")"

  MODEL_ID="$model_id" EXPECTED_OBJECT="$expected_object" INFERENCE_PAYLOAD="$inference_payload" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["INFERENCE_PAYLOAD"])
model_id = os.environ["MODEL_ID"]
expected_object = os.environ["EXPECTED_OBJECT"]

if payload.get("object") != expected_object:
    raise SystemExit(f"{model_id}: expected object '{expected_object}', got '{payload.get('object')}'")
if payload.get("model") != model_id:
    raise SystemExit(f"{model_id}: response reports model '{payload.get('model')}'")
if expected_object == "chat.completion" and not payload["choices"][0]["message"]["content"]:
    raise SystemExit(f"{model_id}: chat completion returned no content")
PY

  printf 'PASS: %s serves %s independently\n' "$model_id" "$route"
done

GATEWAY_URL="http://localhost:${MODEL_GATEWAY_PORT:-8080}"
printf 'Waiting for the gateway at %s/healthz...\n' "$GATEWAY_URL"
for ((attempt = 1; attempt <= TIMEOUT_SECONDS; attempt++)); do
  if curl --silent --fail "$GATEWAY_URL/healthz" >/dev/null 2>&1; then
    break
  fi
  if ((attempt == TIMEOUT_SECONDS)); then
    echo "Gateway did not become ready" >&2
    docker compose -f "$COMPOSE_FILE" logs --no-color model-gateway >&2 || true
    exit 1
  fi
  sleep 1
done

for entry in "${SERVICES[@]}"; do
  IFS=$'\t' read -r model_id port workload secret <<<"$entry"

  routed_payload="$(curl --silent --fail "$GATEWAY_URL/$model_id/v1/models")"
  MODEL_ID="$model_id" MODELS_PAYLOAD="$routed_payload" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["MODELS_PAYLOAD"])
model_id = os.environ["MODEL_ID"]
routed = payload["data"][0]["id"]
if routed != model_id:
    raise SystemExit(f"{model_id}: gateway path routed to '{routed}'")
PY

  printf 'PASS: gateway routes /%s to its own deployment\n' "$model_id"
done

unknown_code="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  "$GATEWAY_URL/not-a-deployment/v1/models")"
if [[ "$unknown_code" != "404" ]]; then
  echo "Gateway returned $unknown_code for an unknown deployment prefix" >&2
  exit 1
fi

printf 'All model services verified\n'
