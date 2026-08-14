from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).parents[3]


def test_model_manifest_declares_selected_runtime_and_license() -> None:
    manifest = json.loads((REPO_ROOT / "models" / "bundle.json").read_text())
    models = {model["id"]: model for model in manifest["models"]}

    assert models["florence-2"]["runtime"] == "transformers"
    assert models["florence-2"]["license"] == "MIT"
    assert models["phi-4-multimodal"]["runtime"] == "onnxruntime-genai-cuda"
    assert models["phi-4-multimodal"]["precision"] == "int4"
    assert models["phi-4-multimodal"]["license"] == "MIT"


def test_bundle_verification_accepts_installed_and_pending_artifacts() -> None:
    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "fetch-model-bundle.sh"), "--verify"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Lock bundle.lock matches the manifest" in result.stdout
    assert "PASS: yolo/model.onnx" in result.stdout
    assert "PENDING: phi-4-multimodal/gpu/gpu-int4-rtn-block-32" in result.stdout