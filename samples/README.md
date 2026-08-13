---
title: Sample Video Inputs
description: Recorded and generated video inputs for local pipeline development
---

## Recorded Input

Do not commit large video files to the repository. Place a local MP4 in this directory and select it with:

```bash
VIDEO_SOURCE_TYPE=file VIDEO_SOURCE=/media/sample.mp4 docker compose up frame-grabber pre-processor
```

The frame-grabber tests create a small recorded MP4 fixture at test time, so CI does not require a committed binary asset.

## RTSP Simulator

The default Compose path generates an FFmpeg test pattern and publishes it to the local MediaMTX RTSP server at `rtsp://localhost:8554/camera-1`. The frame-grabber consumes the corresponding internal URL automatically.