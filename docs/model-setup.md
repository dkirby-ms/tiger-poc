<!-- markdownlint-disable-file -->
# Model Bundle Setup Guide

This guide covers obtaining and setting up the ONNX models required for the Tiger vision pipeline.

## Overview

The Tiger vision pipeline uses three ONNX models:

| Model | Purpose | Source | Size (FP16) | Quantized | VRAM |
|-------|---------|--------|------------|-----------|------|
| YOLO v8 | Object detection | Ultralytics | ~375 MB | ~100 MB (INT8) | 2-3 GB |
| Florence-2 | Vision understanding | Microsoft | ~1.2 GB | ~400 MB (INT8) | 3-4 GB |
| Phi-4-Multimodal | Vision-language reasoning | Microsoft | ~8.5 GB | ~4.3 GB (INT4) | 6-8 GB |

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

### 2. Florence-2

**Official Source:** [Microsoft Florence-2](https://huggingface.co/microsoft/Florence-2-base)

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

3. **Export ONNX:**
   ```bash
   python -c "
from transformers import AutoModelForVision2Seq, AutoProcessor
import torch

model_id = 'microsoft/Florence-2-base'
model = AutoModelForVision2Seq.from_pretrained(model_id, trust_remote_code=True)
processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)

# Export using torch.onnx
dummy_input = torch.randn(1, 3, 1024, 1024)
torch.onnx.export(model, (dummy_input,), 'model.onnx', opset_version=14)
   "
   cp model.onnx ../models/florence-2/model.onnx
   ```

**Note:** The ONNX export process may require additional handling of the model's attention layers and token embeddings. Refer to the Florence repository for the latest export scripts.

### 3. Phi-4-Multimodal

**Official Source:** [Microsoft Phi-4-Multimodal](https://huggingface.co/microsoft/Phi-4-multimodal-instruct)

**Prerequisites:**
- HuggingFace account and API token
- NVIDIA GPU with 24 GB+ VRAM for initial quantization
- torch, transformers, bitsandbytes

#### Setup with INT4 Quantization (Recommended for RTX 5070)

1. **Install dependencies:**
   ```bash
   pip install torch torchvision
   pip install transformers pillow
   pip install bitsandbytes  # For INT4 quantization
   ```

2. **Download and quantize:**
   ```bash
   python -c "
import torch
from transformers import AutoModelForCausalLM, BitsAndBytesConfig
from huggingface_hub import login

# Login to HuggingFace (requires token)
login(token='YOUR_HF_TOKEN')

# Configure INT4 quantization
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type='nf4',
    bnb_4bit_compute_dtype=torch.bfloat16
)

# Load model with quantization
model_id = 'microsoft/Phi-4-multimodal-instruct'
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    quantization_config=bnb_config,
    device_map='auto',
    trust_remote_code=True
)

# Save quantized model
model.save_pretrained('./phi4-int4')
   "
   ```

3. **Export to ONNX:**
   ```bash
   # This requires a custom export script from Microsoft or community
   # See: https://github.com/microsoft/Phi/blob/main/phi-4/export_onnx.py
   python export_onnx.py --model-dir ./phi4-int4 --output-dir models/phi-4-multimodal
   ```

**Alternative:** Use the model directly with ONNX Runtime's Python API without full ONNX export:
```python
import onnxruntime as ort
from transformers import AutoModelForCausalLM

# Load quantized model
model = AutoModelForCausalLM.from_pretrained(
    'microsoft/Phi-4-multimodal-instruct',
    load_in_4bit=True,
    device_map='auto'
)

# Use model with transformers.pipeline
from transformers import pipeline
pipe = pipeline('image-to-text', model=model, device='cuda')
```

## Verification

After obtaining the models, verify they're in place and correctly configured:

```bash
# Run the model fetch script
./scripts/fetch-model-bundle.sh

# Verify models load
docker-compose up -d foundry-local
curl http://localhost:8000/v1/models | python -m json.tool

# Test inference
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "yolo", "messages": [{"role": "user", "content": "test"}]}'
```

## Model Bundle Structure

```
models/
├── bundle.json           # Manifest with model metadata
├── yolo/
│   └── model.onnx       # YOLO v8 (375 MB FP32 / 100 MB INT8)
├── florence-2/
│   └── model.onnx       # Florence-2 (1.2 GB FP16 / 400 MB INT8)
└── phi-4-multimodal/
    └── model.onnx       # Phi-4-Multimodal (8.5 GB FP16 / 4.3 GB INT4)
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
      "format": "onnx",
      "precision": "int8",
      "path": "yolo/model.onnx",
      "sha256": "abc123...",
      "source_url": "https://github.com/ultralytics/assets/releases/..."
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

**Solution:** Use INT4 quantization for Phi-4
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
