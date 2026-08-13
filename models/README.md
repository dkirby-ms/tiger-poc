---
title: Model Bundles
description: Downloaded or generated model bundles for repository applications
---

## Models

The committed [bundle manifest](./bundle.json) defines the model identifiers,
formats, precisions, artifact paths, and digests used by the local runtime.
Model weights are intentionally not committed to Git.

## Fetch And Verify

Configure `source_url` and `sha256` for the artifacts approved for your
environment, then run:

```bash
./scripts/fetch-model-bundle.sh
./scripts/fetch-model-bundle.sh --verify
```

The fetch command downloads only artifacts with a configured source URL. The
verify command checks the manifest schema and every installed artifact. Keep
the generated `bundle.lock` with the manifest when promoting a bundle; it
records the manifest digest used by the runtime.

The default manifest includes YOLO, Florence-2, and an INT4 Phi-4-multimodal
slot. Their source URLs remain empty until the exact ONNX exports and licenses
are approved.
