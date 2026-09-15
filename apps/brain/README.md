---
title: Vision evidence and advisory brain
description: Private observation polling, RAM-only matching JPEGs and separate person-in-zone rules
---

## Implemented boundary

Vision `0.2.0` retains the existing detector's JSONL records and optionally serves
latest observations and matching full-frame JPEGs. Brain `0.1.0` is a separate
Python 3.14 container: HTTP input adapter, validated observation contract,
person-in-zone event mapper, and JSONL stdout sink. It has no production third-party
dependencies. Vision uses its existing OpenCV/Ultralytics/PyTorch dependencies.
Both projects have independent uv locks and Docker test stages.
Source lives in `src/brain.py`, tests in `tests/`, and the dependency manifest,
lock and Dockerfile live at this app's root. The runtime image keeps `/app/brain.py`.

Production vision always uses the real camera and YOLO model. Deterministic
synthetic pixels exist only in tests, never as an inference fallback.
Brain does not run OCR, an LLM, identity recognition, tracking, cloud calls or
hardware actions. Its `clear` means confirmed absence of qualifying predictions,
not a safe area or permission to move machinery. A twin connector is future work.

## Build and test without a camera

From the repository root in PowerShell with WSL Docker:

```powershell
$repo = (wsl -d Ubuntu-24.04 --exec wslpath -a "$PWD").Trim()
wsl -d Ubuntu-24.04 --cd "$repo" --exec docker build --target test -t tiger-vision-tests:brain-integration apps/vision
wsl -d Ubuntu-24.04 --cd "$repo" --exec docker build --target test -t tiger-brain-tests:0.1.0 apps/brain
wsl -d Ubuntu-24.04 --cd "$repo" --exec docker build -t tiger-vision:0.2.0 apps/vision
wsl -d Ubuntu-24.04 --cd "$repo" --exec docker build -t tiger-brain:0.1.0 apps/brain
wsl -d Ubuntu-24.04 --cd "$repo" --exec docker run --rm --network none -e PYTHONPATH=/app/src:/brain -v "${repo}/apps/brain/src/brain.py:/brain/brain.py:ro" -v "${repo}/deploy/local/tests/test_integration.py:/tests/test_integration.py:ro" tiger-vision-tests:brain-integration uv run --no-sync pytest -q /tests/test_integration.py --basetemp=/app/.pytest-integration
```

The first two commands run pytest and Ruff. The loopback test uses actual JPEG
encoding/decoding and HTTP, checks enter/clear/unknown events and exact image
retrieval/expiration, and never saves an image.

For a bounded synthetic two-container smoke, use only the explicit test Compose
file. It does not read the real `.env`, RTSP secret or model:

```powershell
wsl -d Ubuntu-24.04 --cd "$repo" --exec docker compose --env-file /dev/null -p tiger-brain-smoke -f deploy/local/tests/smoke.compose.yaml up -d
Start-Sleep -Seconds 10
wsl -d Ubuntu-24.04 --cd "$repo" --exec docker compose --env-file /dev/null -p tiger-brain-smoke -f deploy/local/tests/smoke.compose.yaml logs --no-log-prefix brain
wsl -d Ubuntu-24.04 --cd "$repo" --exec docker compose --env-file /dev/null -p tiger-brain-smoke -f deploy/local/tests/smoke.compose.yaml exec -T brain python /tests/test_integration.py probe
wsl -d Ubuntu-24.04 --cd "$repo" --exec docker compose --env-file /dev/null -p tiger-brain-smoke -f deploy/local/tests/smoke.compose.yaml down
```

Expect initial `unknown`, then `occupied`, `clear`, `unknown` during a deliberate
input gap, and fresh recovery. The probe fetches one matching JPEG into RAM.
Always run `down`, including after failures. Smoke is a test fixture, not proof
of model accuracy or sustained camera performance.

## Enable real vision and brain explicitly

First follow the [vision setup](../vision/README.md) for trusted weights,
camera authorization, protected RTSP URL file and writable JSONL output directory.
Do not start a camera merely to test the new services.
The original `compose.yaml` alone remains JSONL-only, with no evidence API or JPEG
retention. Add the overlay only when explicitly authorized:

```powershell
wsl -d Ubuntu-24.04 --cd "$repo" --exec docker compose --env-file deploy/local/.env -f deploy/local/compose.yaml -f deploy/local/brain.compose.yaml config --quiet
wsl -d Ubuntu-24.04 --cd "$repo" --exec docker compose --env-file deploy/local/.env -f deploy/local/compose.yaml -f deploy/local/brain.compose.yaml up -d --build
wsl -d Ubuntu-24.04 --cd "$repo" --exec docker compose --env-file deploy/local/.env -f deploy/local/compose.yaml -f deploy/local/brain.compose.yaml logs --no-log-prefix brain
wsl -d Ubuntu-24.04 --cd "$repo" --exec docker compose --env-file deploy/local/.env -f deploy/local/compose.yaml -f deploy/local/brain.compose.yaml down
```

There is one vision worker and one brain per camera. Stream failure terminates
vision, with no automatic reconnection. Brain reports `unknown` and continues
bounded polling until stopped. Service-mode FFmpeg capture open/read calls have
ten-second open and three-second read timeouts. SIGTERM closes the server and drops buffer references;
Compose provides a grace period and eventual termination if native inference hangs.

## Configuration

Settings go in the existing local environment file or an explicit environment.
No camera URL or credentials belong in these settings or API metadata.

| Setting | Default | Contract |
|---------|---------|----------|
| `VISION_SERVICE` | `false` | `true` enables HTTP/JPEG; set by overlay |
| `VISION_BIND_HOST` | `127.0.0.1` | Overlay uses its evidence-network-only DNS alias `vision-evidence` |
| `FRAME_TTL_SECONDS` | `30` | Finite seconds, greater than 0 and at most 300 |
| `FRAME_BUFFER_BYTES` | `67108864` | Encoded JPEG budget, 1 through 268435456 bytes |
| `VISION_URL` | `http://vision:8080` | Brain's private HTTP origin, no credentials/path/query/redirects |
| `CAMERA_ID` | `camera-01` | Must match vision, 1-64 letters, digits, underscores or hyphens |
| `ZONE` | `0,0,1,1` | Left, top, right, bottom in normalized image coordinates; ordered in [0,1] |
| `PERSON_CONFIDENCE` | `0.5` | Finite threshold in [0,1] |
| `ENTER_FRAMES` | `2` | Distinct qualifying observations required, 1-1000 |
| `EXIT_FRAMES` | `3` | Distinct absence observations required, 1-1000 |
| `DWELL_SECONDS` | `0` | Minimum evidence-time span in candidate state, 0-300, applies to enter and exit |
| `STALE_SECONDS` | `5` | Maximum receipt age, 0.1-300 seconds |
| `POLL_SECONDS` | `0.5` | Poll wait, 0.05 through `STALE_SECONDS` |

Presence means a `person` prediction at or above threshold whose bounding-box
center is inside the configured rectangle, inclusive of its edges. This is an
image-space rule, not physical range or a calibrated safety zone.

Counts and dwell advance only on distinct increasing frame numbers. Polling can
skip frames and is not durable delivery or a lossless subscription. Dwell uses
capture age, not time spent polling a duplicate. A stale gap, transport/schema
failure or new session resets confirmation to `unknown`. Recovery needs fresh,
new evidence; a previously processed record cannot restore a state. Retired
sessions and sequence regressions fail closed. Restarting brain loses in-memory
state and starts unknown; event delivery is not exactly-once across brain restarts.

## HTTP observation contract

`GET /v1/observations/latest` returns `200 application/json`:

```json
{
  "schemaVersion": "1.0",
  "available": true,
  "ageSeconds": 0.25,
  "observation": {
    "schemaVersion": "1.0",
    "cameraId": "camera-01",
    "sessionId": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "frameId": "camera-01/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/5",
    "frameNumber": 5,
    "timestamp": "2026-09-14T20:00:00+00:00",
    "capturedAt": "2026-09-14T19:59:59.900000+00:00",
    "processedAt": "2026-09-14T20:00:00+00:00",
    "timestampMeaning": "processing-complete-utc",
    "captureTimestampMeaning": "host-frame-received-utc",
    "frame": {"width": 640, "height": 480},
    "source": {"kind": "rtsp", "cameraId": "camera-01"},
    "model": {"provider": "ultralytics", "sha256": "<trusted model hash>"},
    "detections": [],
    "image": {
      "path": "/v1/frames/camera-01/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/5",
      "mediaType": "image/jpeg",
      "retainedAtPublication": true
    }
  }
}
```

Before the first inference, `observation` and `ageSeconds` are null. Empty
`detections` is valid only for a fresh, available, validated observation; it is
not equivalent to an unavailable service. The service can retain a stale latest
record after its image expires. There is no `/health` readiness claim.

`capturedAt` is host receipt after `capture.read`, not camera exposure time or a
guarantee against upstream RTSP buffering. `processedAt` and legacy `timestamp`
mean inference completion. `ageSeconds` uses a monotonic clock from that receipt
and grows on repeated reads. Brain adds request duration and maintains a local
monotonic deadline; wall-clock changes or repeated polls cannot renew freshness.
Neither service exposes the RTSP URL, model path or full images inside JSON.

`GET /v1/frames/{cameraId}/{sessionId}/{frameNumber}` returns exact matching
`image/jpeg`, never the latest image as a substitute:

* `200`: the named JPEG remains in RAM
* `410`: that past/current ID has expired, was evicted, skipped, or was not retained
* `404`: unknown camera/session, future frame, malformed or unsupported route

`retainedAtPublication` is historical, not a promise the image still exists.
Requests get `Cache-Control: no-store`. `VisionClient.matching_image(observation)`
returns `(status, bytes_or_none)` without saving bytes. Normal brain polling
does not fetch images automatically. Full-frame JPEG only; no crop endpoint.

## Bounds, privacy and trust

Default retention is 30 seconds or 64 MiB encoded JPEG bytes, whichever is reached
first. Oldest-first eviction also caps retained images at 256. Each JPEG is at
most 4 MiB; frames over 16,777,216 pixels are not encoded. TTL is based on
original receipt, so slow inference cannot make an old frame fresh. A periodic
sweep releases expired store references within about 0.5 seconds even when
inference stalls. Current requests can hold immutable bytes for up to the
three-second request lifetime after eviction. No image is written to a file,
log, observation JSONL, model output folder or external service.

The JPEG budget is not the process RSS budget: decoder/model tensors, one
encoding operation, latest JSON, and at most four active responses are additional.
HTTP accepts at most four active requests, uses three-second connection deadlines,
limits accepted paths to 256 characters and headers to 8 KiB after stdlib parsing.
The stdlib parser itself has bounded header count/line sizes. Latest observations
are limited to 256 KiB. Brain bounds JSON and JPEG reads, forbids redirects/proxies,
uses socket/read deadlines and does not retain image history.

No host ports are published. The overlay binds the API to the evidence-network
interface; brain connects only to that internal network. Vision has a separate
camera-egress bridge. This is local network separation, not authentication,
TLS, protection from host/Docker administrators, or a production internet server.
Do not join untrusted containers to the evidence network. Host root can still read
process memory. Compose disables container swap and core dumps for this mode;
host memory dumps, hibernation and privileged inspection remain operator concerns.
Python reference release does not securely overwrite freed memory.

Brain is UID 10002 with read-only root, no capabilities, 128 MiB memory,
0.5 CPU and 32 PIDs. Its event sink is stdout JSONL, bounded by Compose's local
log driver (three 10 MiB files). Outside Compose the caller owns log retention.
Vision's legacy detection JSONL files remain unrotated as before; bound live runs
or manage their disk quota separately. Neither log sink stores images.

## Decision event contract

Events contain `schemaVersion: "1.0"`, `eventType: "ZoneStateChanged"`,
`subjectId: "<camera>:zone"`, `state` (`occupied`, `clear`, `unknown`), `reason`,
UTC decision `timestamp`, `source: "tiger-brain/rules-v1"` and `evidence`.
Confirmed states carry only the exact `frameId`, `capturedAt` and `processedAt`;
unknown carries null evidence. Output occurs only on state changes, not every poll.
No protective action or twin API is implied by an event.
