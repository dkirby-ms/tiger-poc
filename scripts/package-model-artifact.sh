#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: MIT
#
# Push, pull, and verify a model as an ORAS-compatible OCI artifact.

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR="$(dirname "${SCRIPT_DIR}")"
readonly MANIFEST_PATH="${REPO_DIR}/models/bundle.json"

usage() {
  cat <<'EOF'
Usage: package-model-artifact.sh <push|pull|roundtrip> MODEL_ID REFERENCE [OUTPUT_DIR]

Examples:
  package-model-artifact.sh push yolo localhost:5000/models/yolo:dev
  package-model-artifact.sh pull yolo localhost:5000/models/yolo:dev /tmp/yolo
  package-model-artifact.sh roundtrip yolo localhost:5000/models/yolo:dev /tmp/yolo
EOF
}

err() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || err "'$1' command is required"
}

model_field() {
  local model_id="$1"
  local field="$2"
  python3 - "${MANIFEST_PATH}" "${model_id}" "${field}" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
model = next((item for item in manifest["models"] if item["id"] == sys.argv[2]), None)
if model is None:
    raise SystemExit(f"unknown model: {sys.argv[2]}")
print(model[sys.argv[3]])
PY
}

push_model() {
  local model_id="$1"
  local reference="$2"
  local relative_path
  relative_path="$(model_field "${model_id}" path)"
  local artifact_path="${REPO_DIR}/models/${relative_path}"
  [[ -f "${artifact_path}" ]] || err "push currently requires a file artifact: ${artifact_path}"

  oras push \
    --artifact-type application/vnd.tiger.model.v1 \
    --annotation "org.opencontainers.image.title=${model_id}" \
    "${reference}" \
    "${artifact_path}:application/onnx" \
    "${MANIFEST_PATH}:application/vnd.tiger.model.manifest.v1+json"
  oras resolve "${reference}"
}

pull_model() {
  local model_id="$1"
  local reference="$2"
  local output_dir="$3"
  local expected_digest
  expected_digest="$(model_field "${model_id}" sha256)"
  rm -rf "${output_dir}"
  mkdir -p "${output_dir}"
  oras pull "${reference}" --output "${output_dir}"

  local artifact_path="${output_dir}/model.onnx"
  [[ -f "${artifact_path}" ]] || err "pulled artifact does not contain model.onnx"
  local actual_digest
  actual_digest="$(sha256sum "${artifact_path}" | awk '{print $1}')"
  [[ "${actual_digest}" == "${expected_digest}" ]] || err "pulled model digest does not match bundle.json"
  printf 'PASS: %s resolved to %s and verified %s\n' \
    "${model_id}" "$(oras resolve "${reference}")" "${actual_digest}"
}

main() {
  [[ $# -ge 3 && $# -le 4 ]] || {
    usage >&2
    return 2
  }
  require_command oras
  require_command python3
  require_command sha256sum

  local action="$1"
  local model_id="$2"
  local reference="$3"
  local output_dir="${4:-${REPO_DIR}/.artifacts/${model_id}}"
  case "${action}" in
    push)
      push_model "${model_id}" "${reference}"
      ;;
    pull)
      pull_model "${model_id}" "${reference}" "${output_dir}"
      ;;
    roundtrip)
      push_model "${model_id}" "${reference}"
      pull_model "${model_id}" "${reference}" "${output_dir}"
      ;;
    *)
      usage >&2
      return 2
      ;;
  esac
}

main "$@"