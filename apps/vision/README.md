---
title: Tiger vision
description: Run the existing RTSP detector in a pinned CPU-only Python, OpenCV and YOLO environment
---

## Scope

One container runs the `apps/vision/src/rtsp_yolo.py` detector with Python
3.14, OpenCV 4.14.0.94 and Ultralytics 8.4.152. PyTorch 2.14.0 and torchvision
0.29.0 use CPU wheels. The baseline targets Linux amd64; GPU acceleration and
other architectures are not qualified.

OpenCV and YOLO are libraries inside this application, not separate servers.
The optional [separate brain](../brain/README.md) consumes a private observation
API and maps fresh detections to advisory person-in-zone events. No Rover code,
motion control, simulated production detector, cloud provider or ONVIF service
is included. The base Compose file remains JSONL-only.

The detector's CLI flags and JSONL behavior remain compatible. Its processing
function accepts optional observer and capture-factory callbacks. Both the source
CLI and container now use this app's single production manifest and lock; the
older, loosely constrained sample environment has been removed.
`src/package_detector.py` packages execution functions,
omitting the sample CLI and private camera defaults. An AST-equivalence test
protects those function bodies, and an interface change fails the build.
The full sample file is a temporary build input, not copied into image layers.
The app owns its [runtime manifest](pyproject.toml) and [dependency lock](uv.lock),
without notebooks, pytest, ruff or build tooling in the production image.
Python/uv base images are digest-pinned. Debian shared libraries are installed
from the distribution repository at build time; this is not a bit-for-bit
reproducible OS image. Record the built image ID for an exact shared build.

## Build without a camera or model

From the repository root on Linux:

```bash
docker build -t tiger-vision:0.2.0 apps/vision
docker run --rm --network none --read-only --tmpfs /app/runtime:mode=1777 \
  --cap-drop ALL --security-opt no-new-privileges \
  tiger-vision:0.2.0 --check-runtime
```

On Windows using the installed WSL Docker Engine, run from the repository root
in PowerShell:

```powershell
$repo = (wsl -d Ubuntu-24.04 -u root --exec wslpath -a "$PWD").Trim()
wsl -d Ubuntu-24.04 -u root --exec docker build -t tiger-vision:0.2.0 "$repo/apps/vision"
wsl -d Ubuntu-24.04 -u root --exec docker run --rm --network none --read-only --tmpfs /app/runtime:mode=1777 --cap-drop ALL --security-opt no-new-privileges tiger-vision:0.2.0 --check-runtime
```

`--check-runtime` imports the actual vision libraries and exits. It does not load
weights, connect to a camera, run inference or create simulated output. Without
this switch, the image starts real detection only after configuration passes.

## Configure real detection

First obtain approved, trusted Ultralytics-compatible `.pt` weights and their
SHA-256 through the project's model approval process. A hash checks integrity,
not safety or licensing; do not load an untrusted PyTorch checkpoint.
No model is included, downloaded by the build, or automatically fetched at startup.

1. Copy [the environment example](../../deploy/local/.env.example) to
   `deploy/local/.env`, which is ignored by Git.
2. Store the complete RTSP URL in a local UTF-8 file outside the repository.
   Protect it using local file permissions. Never paste camera credentials into
   Git, command-line arguments or shared Compose output.
3. Set `MODEL_FILE`, `RTSP_SECRET_FILE`, `OUTPUT_DIR` to absolute paths and
   `YOLO_MODEL_SHA256` to the model hash. With WSL Docker, use Linux-visible paths
   such as `/mnt/c/...`, not `C:\...`.
4. Create the output directory and grant container UID/GID `10001:10001` write
   access. The model and secret must be readable by that user. For a new Linux
   output directory, `sudo install -d -o 10001 -g 10001 -m 0750 <path>` is sufficient.
   Do not change ownership recursively on existing shared data.
5. Select a non-sensitive `CAMERA_ID`. Set `MAX_FRAMES` to a positive number for
   a bounded initial run, or `0` for continuous detection.

Compose mounts model and secret read-only. Local Compose secrets are file mounts,
not a managed encrypted secret store; protect the source file on the host.
In JSONL-only mode the worker opens no listening ports and uses outbound RTSP over TCP. Host routing,
camera access, VPN and firewall policies still apply. No host networking or
multicast discovery is configured.

## Start and stop

After camera/model authorization and configuration, from the repository root:

```bash
docker compose --env-file deploy/local/.env -f deploy/local/compose.yaml config --quiet
docker compose --env-file deploy/local/.env -f deploy/local/compose.yaml up -d --build vision
docker compose --env-file deploy/local/.env -f deploy/local/compose.yaml logs -f vision
docker compose --env-file deploy/local/.env -f deploy/local/compose.yaml down
```

PowerShell with WSL Docker:

```powershell
$repo = (wsl -d Ubuntu-24.04 -u root --exec wslpath -a "$PWD").Trim()
wsl -d Ubuntu-24.04 -u root --cd "$repo" --exec docker compose --env-file deploy/local/.env -f deploy/local/compose.yaml up -d --build vision
wsl -d Ubuntu-24.04 -u root --cd "$repo" --exec docker compose --env-file deploy/local/.env -f deploy/local/compose.yaml logs -f vision
wsl -d Ubuntu-24.04 -u root --cd "$repo" --exec docker compose --env-file deploy/local/.env -f deploy/local/compose.yaml down
```

The container runs as non-root with read-only root filesystem, dropped capabilities,
2 CPUs, 1536 MiB memory, 128 PIDs and 256 MiB temporary space. These are starting
limits, not measured model capacity guarantees. A model that exceeds them may be
terminated; adjust through a reviewed workload-specific configuration.

In default mode the process is the worker, not an HTTP service. There is no generic "healthy"
endpoint: a running process alone does not prove frames or detections are arriving.
Observe advancing `frameNumber` values in output. Missing configuration exits `2`;
runtime failures exit `1`. Stream disconnects stop the original detector; automatic
reconnection is not implemented. Restart policy is deliberately `no` to avoid
unbounded retry loops with bad camera/model settings. After a successful start,
`docker compose stop vision` invokes the detector's cleanup path.

## Output and integration boundary

Each start writes a new `detections-<UTC>-<unique-id>.jsonl` file in `OUTPUT_DIR`.
Earlier runs and upstream `detections.jsonl` are never reused as output.
Each record retains the existing detector contract:

* `cameraId`, `timestamp`, `frameNumber`
* `detections`: class ID, label, confidence and pixel-coordinate bounding box

Zero detections is a valid processed frame, not a substituted error result.
This is the sample's detection contract, not a digital-twin contract. Opt-in
service mode wraps it in the versioned observation contract documented in the
[brain guide](../brain/README.md), without changing these JSONL records.
Only that mode enables private HTTP and short-lived RAM JPEG retention.
Neither mode records images to disk.

The existing writer has no disk rotation or storage quota. Monitor output disk
space and use `MAX_FRAMES` for bounded runs; memory limits do not limit output
storage. Treat timestamps as detector processing time, not phone capture time.

## Maintain and share

Share the Dockerfile, app runtime manifest/lock, Compose and environment
example through the normal Fork + PR process. Never share `.env`, camera URL files,
private weights, recordings or local output. Publishing an image or branch is a
separate authorized action; this setup does not publish either.

Ultralytics offers [AGPL-3.0 and Enterprise licensing](https://www.ultralytics.com/license).
Confirm the applicable terms with your project's licensing owner before sharing
images or integrating this baseline into a proprietary solution. Model rights
must be assessed separately; installing the package does not approve weights.
Runtime packages retain their installed distribution metadata and license files.

To run the packaging tests without a camera or model:

```bash
docker build --target test -t tiger-vision-tests:brain-integration apps/vision
```

The test stage has the project's dev tools; the final runtime does not. To update
dependencies, edit only this app project through uv in a compatible
Linux/Python 3.14 development environment, regenerate its lock, rebuild and run
the packaging tests and runtime check. Do not combine `opencv-python` and
`opencv-python-headless` in this environment.

## Source detector CLI

The source tree stays flat under `src`; it is not a separately installed package.
Use Python 3.14 on Linux amd64 (including WSL) with the same CPU lock as Docker:

```bash
uv sync --locked --project apps/vision
uv run --locked --project apps/vision apps/vision/src/rtsp_yolo.py --help
```

For an authorized run, provide `RTSP_URL` privately in the environment and
`YOLO_MODEL` as an approved local model path. Keep all flags, including
`--camera-id`, `--confidence`, `--frame-stride`, `--max-frames` and `--output`.
Prefer the guarded container entrypoint for real use: unlike the legacy CLI, it
validates a secret file and model hash and reserves a unique output file.
The CLI retains its legacy app-root model/output defaults and overwrites its
selected output file. Pass `--output data/vision-local/cli-detections.jsonl`
from the repository root to keep generated data out of source.

The old sample `detections.jsonl` was tracked despite containing local evidence.
During layout migration it was preserved, without replay or inspection, at ignored
`data/vision-local/legacy-detector/detections.jsonl`. Existing Git history is unchanged.
No model or evidence file is a build input.
