---
title: Development handoff
description: Working Android RTSP and YOLO container baseline, restart instructions and remaining work
ms.date: 2026-09-14
---

## Where we are

The local camera-to-detection path is working:

```text
Tiger Camera APK
  -> H.264 RTSP over Wi-Fi
  -> vision container: OpenCV + Ultralytics YOLO
  -> local JSONL observations
```

The source, container configuration and Android build are in this contribution.
The image exists locally as `tiger-vision:0.1.0`; it has not been published to a
registry. No cloud resources or separate brain service have been deployed.
Rover remains unchanged and disconnected from this path.

## Delivered components

| Component | Location | Current behavior |
|-----------|----------|------------------|
| Development workflow | `.github`, `lib/hve-core`, `.vscode`, `CONTRIBUTING.md` | Full pinned HVE Core installation; 246 components and 969 managed files |
| Existing detector | `apps/detect/rtsp_yolo.py` | Original source and dependency manifest/lock preserved |
| Vision image | `apps/detect/Dockerfile`, `apps/detect/container` | Python 3.14, OpenCV 4.14, Ultralytics 8.4.152 and CPU PyTorch 2.14 |
| Local deployment | `deploy/vision/compose.yaml` | One non-root worker; external model, RTSP secret and output mounts |
| Android source | `apps/tiger-camera` | Separate Kotlin app with foreground-only Start/Stop and video-only RTSP |
| Local observations | Configured output mount | One JSONL record per processed frame; no image recording |

The camera app uses application ID `org.tigerpoc.camera`, RTSP-Server 1.4.3
and RootEncoder 2.8.1. It was exercised on Android 12 with ARM64 hardware.
Its CLI build uses JDK 17, Gradle 9.7.1, Android Gradle Plugin 9.3.2 and
compile SDK/build tools 37. Android Studio, an emulator and the NDK are not
required. Gradle and dependency checksums/locks are included.

## Observed result on 2026-09-14

The existing vision image decoded live 640x480 H.264 frames from the phone.
RTSP session metadata contained no audio track.

The subsequent Compose run used verified official YOLO26 Nano weights and
produced 20 genuine JSONL records at frame stride 5 and confidence threshold
0.5. Each record contained a `cell phone` prediction, with confidence between
0.7305 and 0.7915. Record timestamps spanned 18 seconds, and the worker exited
successfully at the configured limit.

This demonstrates operation, not independently measured classification accuracy.
No raw images were saved. The bounded worker and its Compose network were
removed after the run; the local model, configuration and observations remain.
The phone's stream is controlled by the user and expires after ten minutes.

Packaging evidence includes 26 focused vision tests, six Android network-policy
unit tests, Android lint without errors, APK installation, and a camera-off
restart with the RTSP listener closed. Older Android versions, alternate lenses,
network-transition cases and the complete lifecycle matrix are not yet qualified.

### Model provenance and capability

The local model came from the official
[Ultralytics assets v8.4.0 release](https://github.com/ultralytics/assets/releases/tag/v8.4.0).
The downloaded `yolo26n.pt` and the checkpoint in fetched upstream history match
the release's SHA-256:

```text
9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef
```

The loaded model reports 80 object classes, including person, bottle, chair,
laptop, keyboard and cell phone. It has no dedicated box or forklift class.
It does not perform facial identification, shipping-label OCR, barcode decoding
or calibrated collision-distance estimation. Review
[Ultralytics licensing](https://www.ultralytics.com/license) before redistribution
or proprietary integration; permission for a local run does not settle those uses.

## Resume local development

The [camera guide](../apps/tiger-camera/README.md) and
[vision guide](../apps/detect/container/README.md) contain the build/setup details.
On a fresh clone, initialize the pinned HVE submodule, provision the documented
CLI prerequisites, build the APK/image and create your own local configuration.
Do not assume another contributor's phone address, model or tool installation.

On the prepared Windows/WSL workstation, from the repository root:

```powershell
$repo = (wsl -d Ubuntu-24.04 -u root --exec wslpath -a "$PWD").Trim()
wsl -d Ubuntu-24.04 -u root --cd "$repo" --exec docker compose --env-file deploy/vision/.env -f deploy/vision/compose.yaml up --no-build --abort-on-container-exit --exit-code-from vision vision
```

Before running it, keep the phone and laptop on the same authorized isolated
Wi-Fi network. Disable cellular/VPN on the phone and leave Tiger Camera in the
foreground. Disable auto-rotate for now, select the lab acknowledgement and tap
Start. If camera permission is requested, grant it and tap Start again.

USB is only needed for installation/debugging; video travels over Wi-Fi.
The configured RTSP address must match the phone's current displayed address.
If DHCP or the network changes, update the local secret file before restarting.
Do not paste credentials or a private camera URL into tracked documentation.

The prepared local configuration uses `MAX_FRAMES=20`, `FRAME_STRIDE=5`,
`CONFIDENCE=0.5` and `CAMERA_ID=tiger-phone-01`.
`MAX_FRAMES` counts processed frames, not every captured frame. The detector
stops automatically at the limit; zero would run continuously and is not the
current configuration.

The worker writes a unique `detections-*.jsonl` under the output mount.
The prepared workstation uses `data/vision-local/observations`.
Records contain `cameraId`, processing-time `timestamp`, `frameNumber` and
`detections` with class, confidence and pixel bounding boxes. They are not yet
the proposed generic observation/event contract.

After a run, remove only that local Compose project's resources:

```powershell
wsl -d Ubuntu-24.04 -u root --cd "$repo" --exec docker compose --env-file deploy/vision/.env -f deploy/vision/compose.yaml down
```

Tap Stop in the phone app when finished. No inference worker was left running
at this handoff.

## Known limitations and next work

1. Rotation currently stops streaming because activity/preview lifecycle changes
   trigger cleanup. Improve rotation handling without allowing background capture.
2. RTSP is lab-only, unencrypted and unauthenticated. The library listens on all
   phone interfaces. The app's network checks cannot prove real network isolation.
3. ONVIF discovery is not implemented. The current source is configured directly
   by RTSP URL; it is not an ONVIF-complete camera.
4. The detector is a one-stream JSONL worker, not an observation API or a
   frame/crop retrieval service. Start with one instance per camera before adding
   multi-stream scheduling or aggregation.
5. Stream reconnect, output rotation/quotas, readiness health reporting and
   sustained performance still need scoped work.
6. A separate brain service and stable downstream observation interface are
   still required. Do not connect Rover's frame-triggered autonomy by default.
7. OCR/barcodes, authorized face recognition and spatial reasoning need their
   own models, contracts and evaluation. Vision must not be the sole protective
   stopping mechanism for a forklift or other machine.
8. Fabric/twin integration, manifest alignment and the deterministic fallback
   remain outside this delivered runtime. No platform-integration claim is made.
9. Source review, image-publication destination and redistribution licensing
   remain before sharing a published container standard.

## Upstream integration boundary

This worktree was based on `3797f0f`. Fetched upstream commits `19c6e6b` and
`7684444` were not merged during the camera/model work. They include updated
design/manifest direction and the model checkpoint. Reconcile those changes
deliberately before a pull request, preserving local design edits and sample
behavior. Re-read current upstream rather than assuming this snapshot is latest.

The earlier separate YOLOX service/demo plan was superseded by packaging the
existing Ultralytics detector. Do not revive that alternate runtime automatically.

## What stays local

Do not commit `.env` files, RTSP secret files, model weights, actual JSONL
recordings, APK/build output, signing keys, downloaded toolchains or caches.
The approved model and local results are reproducible inputs/evidence, not
required source-control payloads. Internal collaboration links and discussions
are not included in this handoff.

These notes were prepared with AI assistance from local implementation evidence.
Maintainer review remains required before publication or production claims.
