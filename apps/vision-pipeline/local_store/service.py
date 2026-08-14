"""Persist detections and sampled clips to a local directory structure."""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel


logger = logging.getLogger(__name__)


class LocalDetectionStore:
    """Write detection records and clips to disk for local workstation testing."""

    def __init__(self, root: str | Path, *, retention_days: int = 7) -> None:
        self.root = Path(root)
        self.retention_days = retention_days
        self.detections_dir = self.root / "detections"
        self.clips_dir = self.root / "clips"
        self.detections_dir.mkdir(parents=True, exist_ok=True)
        self.clips_dir.mkdir(parents=True, exist_ok=True)

    def persist_detection(self, detection: dict[str, Any], *, clip_bytes: bytes | None = None) -> dict[str, Any]:
        """Persist a detection to JSON and optionally store a clip artifact."""

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        record = dict(detection)
        record.setdefault("timestamp", timestamp)
        record.setdefault("camera_id", "camera-1")

        if clip_bytes is not None:
            clip_name = f"{record['camera_id']}-{timestamp}.mp4"
            clip_path = self.clips_dir / clip_name
            clip_path.write_bytes(clip_bytes)
            record["clip_path"] = str(clip_path)
        else:
            record["clip_path"] = None

        detection_path = self.detections_dir / f"{record['camera_id']}-{timestamp}.json"
        detection_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return record

    def list_detections(self) -> list[dict[str, Any]]:
        """Return all persisted detections as JSON payloads."""

        detections: list[dict[str, Any]] = []
        for path in sorted(self.detections_dir.glob("*.json")):
            detections.append(json.loads(path.read_text(encoding="utf-8")))
        return detections

    def purge_expired(self) -> int:
        """Delete detection and clip files older than retention_days."""

        cutoff = datetime.now(timezone.utc).timestamp() - (self.retention_days * 86400)
        deleted = 0
        for pattern in (self.detections_dir.glob("*.json"), self.clips_dir.glob("*.mp4")):
            for path in pattern:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
                    deleted += 1
        return deleted


class PersistDetectionRequest(BaseModel):
    """Request payload for persisting a detection."""

    detection: dict[str, Any]
    source_id: str | None = None
    clip_base64: str | None = None


class PersistenceResponse(BaseModel):
    """Response from persistence operation."""

    success: bool
    detection_path: str | None = None
    message: str


def create_app(store: LocalDetectionStore) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Local Store", version="0.1.0")
    
    @app.get("/healthz")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "detections_dir": str(store.detections_dir),
            "clips_dir": str(store.clips_dir),
        }
    
    @app.post("/persist")
    def persist_detection(request: PersistDetectionRequest) -> PersistenceResponse:
        """Persist a detection to disk."""
        try:
            clip_bytes = (
                base64.b64decode(request.clip_base64)
                if request.clip_base64
                else None
            )
            result = store.persist_detection(request.detection, clip_bytes=clip_bytes)
            detection_path = store.detections_dir / f"{result['camera_id']}-{result['timestamp']}.json"
            logger.info(f"Persisted detection from {request.source_id} to {detection_path}")
            return PersistenceResponse(
                success=True,
                detection_path=str(detection_path),
                message="Detection persisted successfully",
            )
        except Exception as e:
            logger.error(f"Failed to persist detection: {e}")
            return PersistenceResponse(
                success=False,
                detection_path=None,
                message=f"Failed to persist: {str(e)}",
            )
    
    @app.get("/detections")
    def list_detections() -> dict[str, Any]:
        """List all persisted detections."""
        detections = store.list_detections()
        return {
            "count": len(detections),
            "detections": detections,
        }

    @app.get("/clips/{clip_name}")
    def get_clip(clip_name: str) -> FileResponse:
        """Serve a persisted clip file to browser clients."""
        clip_path = store.clips_dir / clip_name
        if not clip_path.exists() or clip_path.is_dir():
            raise HTTPException(status_code=404, detail="Clip not found")
        return FileResponse(path=clip_path, media_type="video/mp4")
    
    @app.post("/purge")
    def purge_expired() -> dict[str, Any]:
        """Purge expired detections and clips."""
        deleted = store.purge_expired()
        return {
            "deleted": deleted,
            "message": f"Purged {deleted} expired files",
        }
    
    return app


def main() -> None:
    """Run the local store server."""
    import uvicorn
    
    parser = argparse.ArgumentParser(description="Local Store server")
    parser.add_argument(
        "--storage-dir",
        default=os.getenv("LOCAL_STORE_DIR", "/data/detections"),
        help="Directory to store detections and clips",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=int(os.getenv("LOCAL_STORE_RETENTION_DAYS", "7")),
        help="Number of days to retain stored data",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("LOCAL_STORE_PORT", "8083")),
        help="Port to listen on",
    )
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    store = LocalDetectionStore(args.storage_dir, retention_days=args.retention_days)
    logger.info(f"Starting Local Store, storing to {args.storage_dir}")
    
    app = create_app(store)
    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
