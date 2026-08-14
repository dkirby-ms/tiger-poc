#!/usr/bin/env bash
# Fetch ONNX model bundle for the Tiger vision pipeline
# Downloads YOLO, Florence-2, and Phi-4-multimodal ONNX models
#
# Note: This is a reference script. Actual model acquisition may require:
# - Authentication (HuggingFace tokens, etc.)
# - Model conversion from PyTorch to ONNX format
# - Quantization for constrained VRAM environments
#
# Usage:
#   ./fetch-model-bundle.sh
#   ./fetch-model-bundle.sh --output-dir ./models --quantize phi-4
#
# Environment variables:
#   MODEL_BUNDLE_DIR    - Output directory for models (default: ./models)
#   HF_TOKEN           - HuggingFace API token (required for some models)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# Configuration
MODEL_BUNDLE_DIR="${MODEL_BUNDLE_DIR:-${REPO_DIR}/models}"
OUTPUT_DIR="${OUTPUT_DIR:-${MODEL_BUNDLE_DIR}}"
BUNDLE_DIR="${BUNDLE_DIR:-${OUTPUT_DIR}}"
QUANTIZE_MODELS="${QUANTIZE_MODELS:-}"
MANIFEST_PATH="${BUNDLE_DIR}/bundle.json"
LOCK_PATH="${BUNDLE_DIR}/bundle.lock"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=== Tiger Vision Pipeline - Model Bundle Fetcher ==="
echo "Output directory: $BUNDLE_DIR"
echo ""

# Create output directory structure
mkdir -p "$BUNDLE_DIR"/{yolo,florence-2,phi-4-multimodal}

# ==============================================================================
# YOLO v8 Model
# ==============================================================================
fetch_yolo() {
    echo -e "${YELLOW}Fetching YOLO v8 model...${NC}"
    
    # YOLO v8 medium model. The official release provides PyTorch weights;
    # export to ONNX locally for the runtime.
    YOLO_PATH="$BUNDLE_DIR/yolo/model.onnx"
    
    if [ -f "$YOLO_PATH" ]; then
        echo -e "${GREEN}  ✓ YOLO model already exists${NC}"
        calculate_hash "$YOLO_PATH"
        return
    fi
    
    export_dir="$(mktemp -d)"
    export_script="from ultralytics import YOLO; YOLO('yolov8m.pt').export(format='onnx', imgsz=640, simplify=False)"
    if command -v uv >/dev/null 2>&1; then
      echo "  Downloading YOLO weights and exporting ONNX with Ultralytics"
      if ! (cd "$export_dir" && uv run --with ultralytics python -c "$export_script"); then
        rm -rf "$export_dir"
        echo -e "${RED}  ✗ Failed to export YOLO model${NC}"
        return 1
      fi
    elif python3 -c "import ultralytics" >/dev/null 2>&1; then
      echo "  Exporting YOLO to ONNX with the installed Ultralytics package"
      if ! (cd "$export_dir" && python3 -c "$export_script"); then
        rm -rf "$export_dir"
        echo -e "${RED}  ✗ Failed to export YOLO model${NC}"
        return 1
      fi
    else
        echo -e "${RED}  ✗ Failed to download YOLO model${NC}"
        echo "    Manual setup required:"
      echo "    1. Install: pip install ultralytics"
      echo "    2. Export: python -c 'from ultralytics import YOLO; YOLO(\"yolov8m.pt\").export(format=\"onnx\")'"
        echo "    3. Copy to: $YOLO_PATH"
      rm -rf "$export_dir"
        return 1
    fi
    mv "$export_dir/yolov8m.onnx" "$YOLO_PATH"
    rm -rf "$export_dir"
    echo -e "${GREEN}  ✓ YOLO model downloaded${NC}"
    calculate_hash "$YOLO_PATH"
}

# ==============================================================================
# Florence-2 Model
# ==============================================================================
fetch_florence2() {
    echo -e "${YELLOW}Fetching Florence-2 model...${NC}"
    
    # Florence-2 is a foundation model for vision understanding
    # Source: Microsoft https://huggingface.co/microsoft/Florence-2-base
    # ~1.2 GB (base), ~2.2 GB (large)
    # Requires PyTorch → ONNX conversion
    #
    # Steps:
    # 1. Clone the repo: git clone https://github.com/microsoft/Florence
    # 2. Install dependencies: pip install -r requirements.txt
    # 3. Export to ONNX: python -m florence.export --model-id microsoft/Florence-2-base
    
      FLORENCE_HF_REPO="microsoft/Florence-2-base"
      FLORENCE_PATH="$BUNDLE_DIR/florence-2"

      if [ -d "$FLORENCE_PATH" ] && find "$FLORENCE_PATH" -type f -print -quit | grep -q .; then
        echo "  Florence-2 artifact already exists"
        return
      fi
      if command -v huggingface-cli >/dev/null 2>&1; then
        huggingface-cli download "$FLORENCE_HF_REPO" --local-dir "$FLORENCE_PATH"
        return
      fi
      echo "  Install huggingface-cli, then run:"
      echo "  pip install -U huggingface_hub"
      echo "  huggingface-cli download $FLORENCE_HF_REPO --local-dir $FLORENCE_PATH"
      return 1
}

# ==============================================================================
# Phi-4-Multimodal Model
# ==============================================================================
fetch_phi4() {
    echo -e "${YELLOW}Fetching Phi-4-Multimodal model...${NC}"
    
    # Phi-4-Multimodal is a lightweight vision-language model
    # Source: Microsoft https://huggingface.co/microsoft/Phi-4-multimodal-instruct
    # ~8.5 GB (FP16), ~4.3 GB (INT4 quantized - recommended for RTX 5070)
    # Requires PyTorch → ONNX conversion
    #
    # For constrained VRAM (12 GB RTX 5070):
    # - Use INT4 quantization (recommended for this scenario)
    # - Consider sequential model loading with YOLO+Florence-2
    
      PHI4_HF_REPO="microsoft/Phi-4-multimodal-instruct-onnx"
      PHI4_PATH="$BUNDLE_DIR/phi-4-multimodal/gpu/gpu-int4-rtn-block-32"

      if [ -d "$PHI4_PATH" ] && find "$PHI4_PATH" -type f -print -quit | grep -q .; then
        echo "  Phi-4 artifact already exists"
        return
      fi
      if command -v huggingface-cli >/dev/null 2>&1; then
        huggingface-cli download "$PHI4_HF_REPO" --include 'gpu/*' --local-dir "$BUNDLE_DIR/phi-4-multimodal"
        return
      fi
      echo "  Install huggingface-cli, then run:"
      echo "  pip install -U huggingface_hub"
      echo "  huggingface-cli download $PHI4_HF_REPO --include 'gpu/*' --local-dir $BUNDLE_DIR/phi-4-multimodal"
      return 1
}

# ==============================================================================
# Helper functions
# ==============================================================================
calculate_hash() {
    local file="$1"
    local hash=$(sha256sum "$file" | awk '{print $1}')
    echo "    SHA256: $hash"
    echo "$hash"
}

update_bundle_json() {
    local bundle_json="$REPO_DIR/models/bundle.json"
    
    if [ ! -f "$bundle_json" ]; then
        echo -e "${RED}✗ bundle.json not found at $bundle_json${NC}"
        return 1
    fi
    
    echo -e "${YELLOW}Updating bundle.json with model checksums...${NC}"
    
    # Update YOLO hash
    if [ -f "$BUNDLE_DIR/yolo/model.onnx" ]; then
      local yolo_hash=$(sha256sum "$BUNDLE_DIR/yolo/model.onnx" | awk '{print $1}')
        python3 -c "
import json
with open('$bundle_json', 'r') as f:
    data = json.load(f)
for model in data.get('models', []):
    if model['id'] == 'yolo':
        model['sha256'] = '$yolo_hash'
with open('$bundle_json', 'w') as f:
    json.dump(data, f, indent=2)
" 2>/dev/null || echo "    (Manual hash update recommended)"
    fi
    
    echo -e "${GREEN}✓ bundle.json updated${NC}"
}

validate_models() {
    echo ""
    echo -e "${YELLOW}=== Model Validation ===${NC}"
    local all_valid=true
    manifest_models="$(mktemp)"
    python3 -c 'import json, sys; [print(model["id"] + "\t" + model["path"]) for model in json.load(open(sys.argv[1], encoding="utf-8"))["models"]]' "$MANIFEST_PATH" > "$manifest_models"
    while IFS=$'\t' read -r model relative_path; do
        model_path="$BUNDLE_DIR/$relative_path"
        if [ -f "$model_path" ] || [ -d "$model_path" ]; then
            size=$(du -sh "$model_path" | awk '{print $1}')
            echo -e "${GREEN}✓${NC} $model ($size)"
        else
            echo -e "${RED}✗${NC} $model (missing)"
            all_valid=false
        fi
    done < "$manifest_models"
    rm -f "$manifest_models"
    
    echo ""
    if [ "$all_valid" = true ]; then
        echo -e "${GREEN}All models present!${NC}"
        echo ""
        echo "Next steps:"
        echo "1. Update bundle.json with sha256 hashes (if not already done)"
        echo "2. Verify models load in Foundry Local: docker-compose up foundry-local"
        echo "3. Test pipeline: ./scripts/test-pipeline-e2e.sh"
    else
        echo -e "${YELLOW}Some models are missing. See instructions above.${NC}"
    fi
}

# ==============================================================================
# Main
# ==============================================================================
usage() {
  cat <<'EOF'
Usage: fetch-model-bundle.sh [--verify] [--write-lock] [--output-dir DIR]

Fetch or validate the model bundle configured in models/bundle.json.
--verify       Validate the manifest, lock file, and installed artifact digests.
--write-lock   Write bundle.lock from the current manifest digest.
--output-dir   Use DIR as the bundle directory.
EOF
}

main() {
  local verify=false
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --verify) verify=true; shift ;;
      --write-lock) WRITE_LOCK=true; shift ;;
      --output|--output-dir) BUNDLE_DIR="$2"; OUTPUT_DIR="$2"; shift 2 ;;
      --quantize) QUANTIZE_MODELS="$2"; shift 2 ;;
      --help|-h) usage; return 0 ;;
      *) usage >&2; return 2 ;;
    esac
  done

  # Keep a single, consistent bundle directory for all operations.
  mkdir -p "$BUNDLE_DIR"

  if [[ "${verify}" == true ]]; then
    verify_bundle
  else
    fetch_yolo || true
    echo ""

    fetch_florence2 || true
    echo ""

    fetch_phi4 || true
    echo ""

    update_bundle_json || true
    validate_models
  fi

  if [[ "${WRITE_LOCK:-false}" == true ]]; then
    write_lock
  fi
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'ERROR: %s is required\n' "$1" >&2
    exit 1
  }
}

verify_bundle() {
  require_command sha256sum
  require_command python3
  python3 - "${MANIFEST_PATH}" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
required = {"bundle_id", "bundle_version", "models"}
missing = required - manifest.keys()
if missing:
    raise SystemExit(f"manifest is missing fields: {', '.join(sorted(missing))}")
for model in manifest["models"]:
    for field in ("id", "format", "precision", "path", "sha256", "source_url"):
        if field not in model:
            raise SystemExit(f"model {model.get('id', '<unknown>')} is missing {field}")
print(f"Manifest {manifest['bundle_id']} v{manifest['bundle_version']} is valid")
PY

  if [[ -f "${LOCK_PATH}" ]]; then
    python3 - "${MANIFEST_PATH}" "${LOCK_PATH}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
lock_path = Path(sys.argv[2])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
lock = json.loads(lock_path.read_text(encoding="utf-8"))
actual_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
if lock.get("manifest_sha256") != actual_digest:
    raise SystemExit("bundle.lock manifest_sha256 does not match bundle.json")
if lock.get("bundle_id") != manifest["bundle_id"]:
    raise SystemExit("bundle.lock bundle_id does not match bundle.json")
if lock.get("bundle_version") != manifest["bundle_version"]:
    raise SystemExit("bundle.lock bundle_version does not match bundle.json")
print(f"Lock {lock_path.name} matches the manifest")
PY
  fi

  manifest_entries="$(mktemp)"
  python3 -c 'import json, sys; [print(model["path"] + "\t" + model["sha256"]) for model in json.load(open(sys.argv[1], encoding="utf-8"))["models"]]' "${MANIFEST_PATH}" > "${manifest_entries}"
  while IFS=$'\t' read -r relative_path expected_digest; do
    [[ -z "${relative_path}" ]] && continue
    artifact_path="${BUNDLE_DIR}/${relative_path}"
    if [[ ! -f "${artifact_path}" && ! -d "${artifact_path}" ]]; then
      printf 'PENDING: %s is not installed\n' "${relative_path}"
      continue
    fi
    if [[ -z "${expected_digest}" ]]; then
      printf 'PRESENT: %s (digest pending)\n' "${relative_path}"
      continue
    fi
    actual_digest="$(sha256sum "${artifact_path}" | awk '{print $1}')"
    if [[ "${actual_digest}" != "${expected_digest}" ]]; then
      printf 'ERROR: digest mismatch for %s\n' "${relative_path}" >&2
      exit 1
    fi
    printf 'PASS: %s\n' "${relative_path}"
  done < "${manifest_entries}"
  rm -f "${manifest_entries}"
}

fetch_bundle() {
  require_command curl
  require_command python3
  mkdir -p "${BUNDLE_DIR}"
  while IFS=$'\t' read -r relative_path source_url expected_digest; do
    artifact_path="${BUNDLE_DIR}/${relative_path}"
    if [[ -z "${source_url}" ]]; then
      printf 'SKIP: no source_url configured for %s\n' "${relative_path}"
      continue
    fi
    mkdir -p "$(dirname "${artifact_path}")"
    curl --fail --location --show-error --output "${artifact_path}.part" "${source_url}"
    mv "${artifact_path}.part" "${artifact_path}"
    if [[ -n "${expected_digest}" ]]; then
      actual_digest="$(sha256sum "${artifact_path}" | awk '{print $1}')"
      [[ "${actual_digest}" == "${expected_digest}" ]] || {
        printf 'ERROR: digest mismatch for %s\n' "${relative_path}" >&2
        exit 1
      }
    fi
    printf 'FETCHED: %s\n' "${relative_path}"
  done < <(python3 - "${MANIFEST_PATH}" <<'PY'
import json
import sys
from pathlib import Path

for model in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["models"]:
    print(f"{model['path']}\t{model['source_url']}\t{model['sha256']}")
PY
)
}

write_lock() {
  require_command sha256sum
  manifest_digest="$(sha256sum "${MANIFEST_PATH}" | awk '{print $1}')"
  python3 - "${MANIFEST_PATH}" "${LOCK_PATH}" "${manifest_digest}" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
lock = {
    "bundle_id": manifest["bundle_id"],
    "bundle_version": manifest["bundle_version"],
    "manifest_sha256": sys.argv[3],
}
Path(sys.argv[2]).write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
PY
  printf 'WROTE: %s\n' "${LOCK_PATH}"
}

main "$@"

