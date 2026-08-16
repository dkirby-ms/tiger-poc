"""Resolve on-disk model bundle paths from the bundle manifest.

`models/bundle.json` maps a bundle model id to a path relative to the bundle
directory. `MODEL_BUNDLE_DIR` overrides the bundle directory, matching
`scripts/fetch-model-bundle.sh`.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

DEFAULT_BUNDLE_DIR = Path(__file__).resolve().parents[2] / "models"


def bundle_dir() -> Path:
    """Root directory containing `bundle.json` and model artifacts."""
    return Path(os.environ.get("MODEL_BUNDLE_DIR", str(DEFAULT_BUNDLE_DIR)))


@lru_cache(maxsize=None)
def _manifest(root: str) -> dict:
    manifest_path = Path(root) / "bundle.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def resolve_bundle_path(bundle_model_id: str, root: Optional[Path] = None) -> Optional[Path]:
    """Return the absolute path for a bundle entry, or `None` if unavailable."""
    manifest_root = root or bundle_dir()
    try:
        manifest = _manifest(str(manifest_root))
    except (OSError, json.JSONDecodeError):
        return None
    for entry in manifest.get("models", []):
        if entry.get("id") == bundle_model_id:
            path = manifest_root / entry["path"]
            return path if path.exists() else None
    return None
