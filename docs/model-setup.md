<!-- markdownlint-disable-file -->
# Model Bundle Setup Guide

This guide covers obtaining and setting up the ONNX models required for the Tiger vision pipeline.

## Overview

The Tiger vision pipeline uses three model runtimes:

| Model | Purpose | Source | Size (FP16) | Quantized | VRAM |
|-------|---------|--------|------------|-----------|------|
| YOLO v8 | Object detection | Ultralytics | ~375 MB | ~100 MB (INT8) | 2-3 GB |
| Florence-2 | Vision understanding | Microsoft Transformers/Safetensors | ~1.2 GB | Runtime-dependent | 3-4 GB |
| Phi-4-Multimodal | Vision-language reasoning | Microsoft ONNX Runtime GenAI | ~5.14 GB | GPU INT4 | 6-8 GB |

**RTX 5070 VRAM Budget:** 12 GB total
- YOLO + Florence-2 concurrent: ~5-7 GB
- Phi-4-Multimodal: ~6-8 GB
- **Recommendation:** Use INT4 quantization for Phi-4 and INT8 for others

## Model Acquisition

### 1. YOLO v8

**Official Source:** [Ultralytics YOLO](https://github.com/ultralytics/ultralytics)

#### Option A: Direct Download (Recommended)
```bash
cd models/yolo
curl -L https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8m.onnx -o model.onnx
```

#### Option B: Export from PyTorch
```bash
pip install ultralytics
python -c "from ultralytics import YOLO; YOLO('yolov8m.pt').export(format='onnx')"
cp runs/detect/predict/yolov8m.onnx models/yolo/model.onnx
```

#### Option C: HuggingFace
```bash
pip install huggingface-hub
huggingface-cli download Ultralytics/YOLO-v8 --include "yolov8m.onnx"
```

### 2. Florence-2 Transformers Runtime

**Official Source:** [Microsoft Florence-2](https://huggingface.co/microsoft/Florence-2-base)

The official Microsoft release is MIT-licensed and distributed as a
Transformers model. It is not treated as a single-file ONNX artifact in this
bundle.

#### Setup

1. **Clone the Florence repository:**
   ```bash
   git clone https://github.com/microsoft/Florence
   cd Florence
   ```

2. **Install dependencies:**
   ```bash
   pip install torch torchvision torchaudio
   pip install transformers pillow peft timm einops
   ```

3. **Download the official model files:**
   ```bash
   huggingface-cli download microsoft/Florence-2-base \
     --local-dir models/florence-2
   ```

### 3. Phi-4-Multimodal ONNX Runtime GenAI

**Official Source:** [Microsoft Phi-4-Multimodal ONNX](https://huggingface.co/microsoft/Phi-4-multimodal-instruct-onnx)

The official Microsoft ONNX repository is MIT-licensed and provides a GPU
INT4 model directory at `gpu/gpu-int4-rtn-block-32`. It uses ONNX Runtime
GenAI rather than `onnxruntime.InferenceSession`.

#### Setup with the official GPU INT4 artifact

1. **Install the GenAI runtime:**
   ```bash
   pip install --pre onnxruntime-genai-cuda
   ```

2. **Download the Microsoft artifact:**
   ```bash
   huggingface-cli download microsoft/Phi-4-multimodal-instruct-onnx \
     --include 'gpu/*' --local-dir models/phi-4-multimodal
   ```

3. **Run the official multimodal sample:**
   ```bash
   python model-mm.py \
     -m models/phi-4-multimodal/gpu/gpu-int4-rtn-block-32 \
     -e cuda
   ```

## Verification

After obtaining the models, verify they're in place and correctly configured:

```bash
# Download artifacts and update their deterministic SHA-256 digests
PATH="$PWD/apps/vision-pipeline/.venv/bin:$PATH" ./scripts/fetch-model-bundle.sh --write-lock

# Verify artifact digests and manifest lock
PATH="$PWD/apps/vision-pipeline/.venv/bin:$PATH" ./scripts/fetch-model-bundle.sh --verify

# Build, start, probe, and clean up the local model runtime
./scripts/verify-local-model-runtime.sh
```

## Model Bundle Structure

```
models/
├── bundle.json           # Manifest with model metadata
├── yolo/
│   └── model.onnx       # YOLO v8 (375 MB FP32 / 100 MB INT8)
├── florence-2/           # Official Transformers/Safetensors files
└── phi-4-multimodal/
   └── gpu/              # Official ORT GenAI model directory
      └── gpu-int4-rtn-block-32/
```

## bundle.json Format

```json
{
  "bundle_id": "tiger-vision-models",
  "bundle_version": "0.1.0",
  "description": "Model manifest for the Tiger vision pipeline",
  "models": [
    {
      "id": "yolo",
      "format": "onnx-genai",
      "precision": "int4",
      "path": "phi-4-multimodal/gpu/gpu-int4-rtn-block-32",
      "sha256": "abc123...",
      "source_url": "https://huggingface.co/microsoft/Phi-4-multimodal-instruct-onnx",
      "license": "MIT",
      "runtime": "onnxruntime-genai-cuda"
    }
  ]
}
```

The `sha256` field should be populated after obtaining the actual model files:
```bash
sha256sum models/yolo/model.onnx | awk '{print $1}'
```

## VRAM Budget Analysis

### Scenario 1: YOLO + Florence-2 (Concurrent)
- YOLO v8 (FP16): ~2 GB
- Florence-2 (FP16): ~3 GB
- Inference API overhead: ~1 GB
- **Total:** ~6 GB (comfortable within 12 GB RTX 5070)

### Scenario 2: Adding Phi-4-Multimodal
- YOLO + Florence-2: ~5 GB
- Phi-4-Multimodal (FP16): ~8 GB
- **Total:** ~13 GB ❌ Exceeds budget

**Solution:** Use the official Microsoft GPU INT4 ORT GenAI artifact for Phi-4
- Phi-4-Multimodal (INT4): ~4-5 GB
- YOLO + Florence-2 + Phi-4 (INT4): ~9-10 GB ✓

## Troubleshooting

### Model Won't Load
- **Check model format:** Verify ONNX opset version compatibility (recommend opset 14+)
- **Check CUDA availability:** `nvidia-smi` should show GPU memory
- **Check ONNX Runtime:** `python -c "import onnxruntime; print(onnxruntime.get_available_providers())"`

### Out of Memory (OOM) Errors
- Use quantized models (INT4/INT8)
- Reduce batch size in pre-processor
- Consider sequential model loading (don't load all models simultaneously)

### Model Download Failures
- Check internet connectivity and firewall rules
- Verify HuggingFace API token if required
- Use alternative download methods (manual download, git-lfs)

## References

- [Ultralytics YOLO](https://github.com/ultralytics/ultralytics)
- [Microsoft Florence-2](https://github.com/microsoft/Florence)
- [Microsoft Phi-4-Multimodal](https://github.com/microsoft/Phi)
- [ONNX Runtime Documentation](https://onnxruntime.ai/)
- [BitsAndBytes Quantization](https://github.com/TimDettmers/bitsandbytes)
