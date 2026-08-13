---
title: Vision Pipeline Application
description: Source boundary for the local computer vision pipeline application
---

## Vision Pipeline

Application source for the local computer vision pipeline belongs in this directory.

Epic 2 services:

* `frame_grabber.service` samples recorded or RTSP video and publishes JPEG frames
* `frame_grabber.receiver` provides the temporary pre-processor HTTP boundary

Install development dependencies and run tests from this directory:

```bash
python -m pip install -e '.[test]'
pytest
```
