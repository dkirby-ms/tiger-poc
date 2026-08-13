#!/usr/bin/env bash
# End-to-end pipeline integration test
# Tests the full vision pipeline from frame ingestion through storage

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# Configuration
COMPOSE_FILE="$REPO_DIR/docker-compose.yml"
FOUNDRY_URL="http://localhost:8000"
INFERENCE_API_URL="http://localhost:8081"
EVENT_RULES_URL="http://localhost:8082"
LOCAL_STORE_URL="http://localhost:8083"
TIMEOUT=60
DETECTIONS_DIR="$REPO_DIR/data/detections/detections"
CLIPS_DIR="$REPO_DIR/data/detections/clips"
VIDEO_SOURCE_TYPE="${VIDEO_SOURCE_TYPE:-$(sed -n 's/^VIDEO_SOURCE_TYPE=//p' "$REPO_DIR/.env" | head -1)}"
VIDEO_SOURCE="${VIDEO_SOURCE:-$(sed -n 's/^VIDEO_SOURCE=//p' "$REPO_DIR/.env" | head -1)}"

echo "=== Tiger Vision Pipeline E2E Test ==="
echo "Testing pipeline with containers..."

# Clean up on exit
cleanup() {
    echo "Cleaning up..."
    docker-compose -f "$COMPOSE_FILE" down || true
}
trap cleanup EXIT

# Start the pipeline
echo "Starting pipeline..."
docker-compose -f "$COMPOSE_FILE" up -d --build

if [[ "${VIDEO_SOURCE_TYPE:-rtsp}" != "rtsp" || -z "${VIDEO_SOURCE:-}" ]]; then
  echo "✗ VIDEO_SOURCE_TYPE=rtsp and VIDEO_SOURCE must be configured for this test"
  exit 1
fi

DETECTIONS_BEFORE=$(find "$DETECTIONS_DIR" -maxdepth 1 -type f -name '*.json' 2>/dev/null | wc -l)
CLIPS_BEFORE=$(find "$CLIPS_DIR" -maxdepth 1 -type f -name '*.mp4' 2>/dev/null | wc -l)

# Wait for services to be ready
echo "Waiting for services to start..."
for service_url in "$FOUNDRY_URL" "$INFERENCE_API_URL" "$EVENT_RULES_URL" "$LOCAL_STORE_URL"; do
    echo "  Checking $service_url..."
    for i in $(seq 1 "$TIMEOUT"); do
        if curl -s "$service_url/healthz" > /dev/null 2>&1; then
            echo "    ✓ Ready"
            break
        fi
        if [ $i -eq "$TIMEOUT" ]; then
            echo "    ✗ Timeout waiting for $service_url"
            exit 1
        fi
        sleep 1
    done
done

echo ""
echo "=== Service Health Checks ==="
echo "Foundry Local:"
curl -s "$FOUNDRY_URL/healthz" | python3 -m json.tool

echo ""
echo "Inference API:"
curl -s "$INFERENCE_API_URL/healthz" | python3 -m json.tool

echo ""
echo "Event Rules:"
curl -s "$EVENT_RULES_URL/healthz" | python3 -m json.tool

echo ""
echo "Local Store:"
curl -s "$LOCAL_STORE_URL/healthz" | python3 -m json.tool

echo ""
echo "=== Testing Pipeline Flow ==="
echo "Waiting for the configured RTSP feed to produce a detection and clip..."
for i in $(seq 1 "$TIMEOUT"); do
    DETECTION_COUNT=$(find "$DETECTIONS_DIR" -maxdepth 1 -type f -name '*.json' 2>/dev/null | wc -l)
    CLIP_COUNT=$(find "$CLIPS_DIR" -maxdepth 1 -type f -name '*.mp4' 2>/dev/null | wc -l)
    if [[ "$DETECTION_COUNT" -gt "$DETECTIONS_BEFORE" && "$CLIP_COUNT" -gt "$CLIPS_BEFORE" ]]; then
        break
    fi
    if [[ "$i" -eq "$TIMEOUT" ]]; then
        echo "✗ Timed out waiting for RTSP detections and clips"
        docker-compose -f "$COMPOSE_FILE" logs --no-color --tail=80 frame-grabber pre-processor inference-api local-store
        exit 1
    fi
    sleep 1
done

LATEST_DETECTION=$(find "$DETECTIONS_DIR" -maxdepth 1 -type f -name '*.json' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)
LATEST_CLIP=$(find "$CLIPS_DIR" -maxdepth 1 -type f -name '*.mp4' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)
echo "Latest detection: $LATEST_DETECTION"
echo "Latest clip: $LATEST_CLIP"
python3 - "$LATEST_DETECTION" "$LATEST_CLIP" <<'PY'
import json
import sys
from pathlib import Path

detection = json.loads(Path(sys.argv[1]).read_text())
clip = Path(sys.argv[2])
if not detection.get("clip_path") or not clip.is_file() or clip.stat().st_size == 0:
    raise SystemExit("Detection is missing a non-empty clip")
print(f"Detection label: {detection.get('label')}")
print(f"Clip size: {clip.stat().st_size} bytes")
PY

DETECTION_COUNT=$(find "$DETECTIONS_DIR" -maxdepth 1 -type f -name '*.json' | wc -l)
CLIP_COUNT=$(find "$CLIPS_DIR" -maxdepth 1 -type f -name '*.mp4' | wc -l)

echo ""
echo "=== Test Results ==="
if [ "$DETECTION_COUNT" -gt "$DETECTIONS_BEFORE" ] && [ "$CLIP_COUNT" -gt "$CLIPS_BEFORE" ]; then
  echo "✓ RTSP frames produced detections and clips successfully!"
    exit 0
else
  echo "✗ Pipeline test failed: no new detection clip was produced"
    exit 1
fi
