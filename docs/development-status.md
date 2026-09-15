---
title: Development handoff
description: Working camera baseline and tested private vision evidence API with separate advisory brain
ms.date: 2026-09-15
---

## Where we are

The local camera-to-decision path has been exercised in landscape and portrait:

```text
Tiger Camera APK
  -> H.264 RTSP over Wi-Fi
  -> vision container: OpenCV + Ultralytics YOLO
  -> local JSONL observations and private evidence API
  -> separate rules brain
  -> occupied / clear / unknown advisory events
```

The source, container configuration and Android build are in this contribution.
The historical live run used `tiger-vision:0.1.0`. The new local images are
`tiger-vision:0.2.0` and `tiger-brain:0.1.0`; neither has been published to a
registry. No cloud resources have been deployed.
Rover remains unchanged and disconnected from this path.

The new opt-in stage adds private latest-observation polling, exact RAM JPEG
retrieval and a separate advisory person-in-zone brain. Default retention is
30 seconds or 64 MiB, whichever is reached first.
Synthetic integration and bounded live runs have exercised this stage, including
portrait person detections with the latest installed APK. Sustained performance
and the full device/lens/lifecycle matrix are not established.
See the [brain and evidence guide](../apps/brain/README.md) for its contract,
configuration, isolated smoke and explicit real-camera overlay commands.

## Delivered components

| Component | Location | Current behavior |
|-----------|----------|------------------|
| Development workflow | `.github`, `lib/hve-core`, `.vscode`, `CONTRIBUTING.md` | Full pinned HVE Core installation; 246 components and 969 managed files |
| Existing detector | `apps/vision/src/rtsp_yolo.py` | Compatible CLI/JSONL and observer/capture-factory seam; one app-level production manifest/lock |
| Vision image | `apps/vision/Dockerfile`, `apps/vision/src`, `apps/vision/tests` | Python 3.14, OpenCV 4.14, Ultralytics 8.4.152 and CPU PyTorch 2.14 |
| Local deployment | `deploy/local/compose.yaml` | One non-root worker; external model, RTSP secret and output mounts |
| Android source | `apps/tiger-camera` | Separate Kotlin app with foreground auto-start, manual Stop/Start and video-only RTSP; no acknowledgement checkbox |
| Local observations | Configured output mount | One JSONL record per processed frame; no image recording |
| Evidence service | `apps/vision/src/observation_service.py` | Opt-in versioned latest JSON and exact JPEG by camera/session/frame ID, bounded RAM |
| Advisory brain | `apps/brain/src`, `apps/brain/tests` | Separate Python 3.14 image, validated person-in-zone rules and JSONL state events |
| Private integration | `deploy/local/brain.compose.yaml`, `deploy/local/tests` | No host ports; dedicated internal evidence network and bounded logs/resources |

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

### Subsequent vision and brain validation

The opt-in integration was built and tested separately after that live run:

* Vision test image: 35 passing tests, including the original 26
* Brain test image: 33 passing tests
* Cross-service loopback: 2 passing tests with synthetic pixels, actual JPEG
  encoding/decoding, exact HTTP retrieval and bounded/truncated transport checks
* Both production Docker images built; vision runtime imports checked without a
  camera, model or network
* Isolated two-container smoke: advisory `unknown`, `occupied`, `clear`, stale
  `unknown`, then fresh `occupied`; matching JPEG fetched only into memory
* Smoke processes exited successfully and their containers/network were removed

The source includes reusable synthetic smoke configuration, not a production
fake-detector option. The new HTTP API is trusted-local and must not be published
to an untrusted network.

### Live rules-brain result later that evening

An authorized landscape run processed 20 frames at the unchanged 0.5 confidence
threshold. Thirteen frames included a person prediction, with confidence
0.6453-0.9194, followed by seven frames without a person prediction. The brain
emitted `unknown`, `occupied`, `clear`, then `unknown` when the bounded vision
worker exited successfully. These states describe model evidence, not verified
physical occupancy or permission to move machinery.

The brain client also retrieved an exactly correlated 640x480 JPEG, 37,452 bytes,
into RAM. No image was saved or visually inspected. Earlier portrait attempts
did not produce qualifying person predictions. Landscape success does not isolate
orientation, framing, lighting or distance as the cause of that difference.

The live run exposed a cold-inference dependency on Python's temporary directory.
The runtime now sets `TMPDIR=/app/runtime`, using its existing bounded RAM-backed
mount instead of the read-only root filesystem. A read-only, network-disabled
runtime import and subsequent real inference exercised that correction.
The first prediction took about 17 seconds from host frame receipt during warmup;
the brain rejected that stale evidence rather than reporting occupied early.
Later sampled observations were generally about 0.9-1.6 seconds old.

Those test containers and networks were removed. No camera or inference session
should run unattended; opening the current phone app can auto-start capture.

### Camera orientation increment

The updated Android source preserves preview proportions and uses RootEncoder's
display-relative rotation contract. Landscape sessions encode 640x480; portrait
sessions encode 480x640. The camera-source request remains 640x480 and no extra
sensor rotation is applied. Orientation is locked for an explicit streaming
session and restored on cleanup. Stop before rotating and start again afterward;
if Android changes the display despite the lock, capture stops without restarting.

The orientation increment initially passed 23 geometry, session and network-policy
tests and Android lint. The latest APK, including foreground auto-start, has since
been installed and exercised with real portrait person detections and brain rule
events. The landscape evidence above belongs to the earlier app.
Both lenses, reverse orientations, visible proportions and the complete device
lifecycle matrix still need qualification.
See the [camera guide](../apps/tiger-camera/README.md#orientation-and-preview)
for the exact qualification steps.

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
[vision guide](../apps/vision/README.md) contain the build/setup details.
On a fresh clone, initialize the pinned HVE submodule, provision the documented
CLI prerequisites, build the APK/image and create your own local configuration.
Do not assume another contributor's phone address, model or tool installation.

On the prepared Windows/WSL workstation, from the repository root:

```powershell
$repo = (wsl -d Ubuntu-24.04 -u root --exec wslpath -a "$PWD").Trim()
wsl -d Ubuntu-24.04 -u root --cd "$repo" --exec docker compose --env-file deploy/local/.env -f deploy/local/compose.yaml up --no-build --abort-on-container-exit --exit-code-from vision vision
```

Before running it, keep the phone and laptop on the same authorized isolated
Wi-Fi network. Disable cellular/VPN on the phone and leave Tiger Camera in the
foreground. The current APK fixes orientation per session and automatically starts
after camera permission and network checks pass; there is no lab acknowledgement
checkbox. Manual Stop keeps capture stopped until you tap Start. Stop before
rotating, then tap Start again.

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
wsl -d Ubuntu-24.04 -u root --cd "$repo" --exec docker compose --env-file deploy/local/.env -f deploy/local/compose.yaml down
```

Tap Stop in the phone app when finished. Check the current project state before
running lifecycle commands; existing containers were not restarted or stopped
during the repository layout cleanup. Use the original project name (for example,
`-p tiger-live`) when intentionally managing an existing deployment.

## Known limitations and next work

1. The aspect-preserving, per-session orientation implementation needs broader device
   qualification beyond the observed portrait run. Changing orientation requires
   Stop, rotate, then Start. Foreground auto-start is supported, but background
   capture and automatic recovery of a failed stream are not.
2. RTSP is lab-only, unencrypted and unauthenticated. The library listens on all
   phone interfaces. The app's network checks cannot prove real network isolation.
3. ONVIF discovery is not implemented. The current source is configured directly
   by RTSP URL; it is not an ONVIF-complete camera.
4. The worker remains one-stream. Its opt-in observation API provides latest
   polling and exact full JPEGs, not crops, replay, durable subscriptions or
   multi-stream scheduling.
5. Stream reconnect, output rotation/quotas, readiness health reporting and
   sustained performance still need scoped work.
6. The separate rules brain now maps versioned observations to advisory zone
   events. Broader ontology/twin mappings, authentication and fleet/session
   persistence remain follow-up work. Rover autonomy is not connected.
7. OCR/barcodes, authorized face recognition and spatial reasoning need their
   own models, contracts and evaluation. Vision must not be the sole protective
   stopping mechanism for a forklift or other machine.
8. Fabric/twin integration, manifest alignment and the deterministic fallback
   remain outside this delivered runtime. No platform-integration claim is made.
9. Source review, image-publication destination and redistribution licensing
   remain before sharing a published container standard.

### Future animated face interface

The requested Rover-style face is a presentation capability, separate from
facial recognition. Rover's
[eye display source](https://github.com/lovelacer74/hve-copilot-rover/tree/1ca5565f6e37c00da61db9a555bb666b0c00c7bb/android/app/src/main/java/com/copilot/rover/ui/eyes)
separates expression state, drawing primitives and themes. Its Compose screen
also references Rover voice-interaction state; it is not a drop-in widget for
Tiger's current native Activity.

A future display adapter can map brain and connection events to expressions
without embedding camera, inference or motor logic in the renderer. That requires
an explicitly secured phone-facing status connection; the current evidence API
is intentionally internal to Docker and not reachable by the phone. Voice,
identity recognition and hardware control are not prerequisites for animated eyes.
Confirm the exact renderer modules and behavior before porting; no Rover
application code or identity assets have been copied into Tiger.

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
