---
title: Shared vision container
description: Run the existing RTSP detector in a pinned CPU-only Python, OpenCV and YOLO environment
---

## Scope

One container runs the existing `apps/detect/rtsp_yolo.py` application with Python
3.14, OpenCV 4.14.0.94 and Ultralytics 8.4.152. PyTorch 2.14.0 and torchvision
0.29.0 use CPU wheels. The baseline targets Linux amd64; GPU acceleration and
other architectures are not qualified.

OpenCV and YOLO are libraries inside this application, not separate servers.
A future Rover-derived brain belongs in another container and consumes an agreed
output interface. No brain, motion control, Android app, simulated detector, cloud
provider or ONVIF discovery service is included here.

The original detector and its Python environment remain unchanged in the repository.
The build packages its unchanged validation, detection and processing functions,
omitting the sample CLI and private camera defaults. An AST-equivalence test
protects those function bodies, and an interface change fails the build.
The full sample file is a temporary build input, not copied into image layers.
The container
has its own [runtime manifest](pyproject.toml) and [dependency lock](uv.lock),
without notebooks, pytest, ruff or build tooling in the production image.
Python/uv base images are digest-pinned. Debian shared libraries are installed
from the distribution repository at build time; this is not a bit-for-bit
reproducible OS image. Record the built image ID for an exact shared build.

## Build without a camera or model

From the repository root on Linux:

```bash
docker build -t tiger-vision:0.1.0 apps/detect
docker run --rm --network none --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges \
  tiger-vision:0.1.0 --check-runtime
```

On Windows using the installed WSL Docker Engine, run from the repository root
in PowerShell:

```powershell
$repo = (wsl -d Ubuntu-24.04 -u root --exec wslpath -a "$PWD").Trim()
wsl -d Ubuntu-24.04 -u root --exec docker build -t tiger-vision:0.1.0 "$repo/apps/detect"
wsl -d Ubuntu-24.04 -u root --exec docker run --rm --network none --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges tiger-vision:0.1.0 --check-runtime
```

`--check-runtime` imports the actual vision libraries and exits. It does not load
weights, connect to a camera, run inference or create simulated output. Without
this switch, the image starts real detection only after configuration passes.

## Configure real detection

First obtain approved, trusted Ultralytics-compatible `.pt` weights and their
SHA-256 through the project's model approval process. A hash checks integrity,
not safety or licensing; do not load an untrusted PyTorch checkpoint.
No model is included, downloaded by the build, or automatically fetched at startup.

1. Copy [the environment example](../../../deploy/vision/.env.example) to
   `deploy/vision/.env`, which is ignored by Git.
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
The service opens no listening ports and uses outbound RTSP over TCP. Host routing,
camera access, VPN and firewall policies still apply. No host networking or
multicast discovery is configured.

## Start and stop

After camera/model authorization and configuration, from the repository root:

```bash
docker compose --env-file deploy/vision/.env -f deploy/vision/compose.yaml config --quiet
docker compose --env-file deploy/vision/.env -f deploy/vision/compose.yaml up -d --build vision
docker compose --env-file deploy/vision/.env -f deploy/vision/compose.yaml logs -f vision
docker compose --env-file deploy/vision/.env -f deploy/vision/compose.yaml down
```

PowerShell with WSL Docker:

```powershell
$repo = (wsl -d Ubuntu-24.04 -u root --exec wslpath -a "$PWD").Trim()
wsl -d Ubuntu-24.04 -u root --cd "$repo" --exec docker compose --env-file deploy/vision/.env -f deploy/vision/compose.yaml up -d --build vision
wsl -d Ubuntu-24.04 -u root --cd "$repo" --exec docker compose --env-file deploy/vision/.env -f deploy/vision/compose.yaml logs -f vision
wsl -d Ubuntu-24.04 -u root --cd "$repo" --exec docker compose --env-file deploy/vision/.env -f deploy/vision/compose.yaml down
```

The container runs as non-root with read-only root filesystem, dropped capabilities,
2 CPUs, 1536 MiB memory, 128 PIDs and 256 MiB temporary space. These are starting
limits, not measured model capacity guarantees. A model that exceeds them may be
terminated; adjust through a reviewed workload-specific configuration.

The process is the worker, not an HTTP service. There is no generic "healthy"
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
This is the sample's detection contract, not yet the generic Tiger observation
or digital-twin contract. A future brain adapter must explicitly consume/map it.
There is no network publication or raw-image recording in this baseline.

The existing writer has no disk rotation or storage quota. Monitor output disk
space and use `MAX_FRAMES` for bounded runs; memory limits do not limit output
storage. Treat timestamps as detector processing time, not phone capture time.

## Maintain and share

Share the Dockerfile, container runtime manifest/lock, Compose and environment
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
docker build --target test -t tiger-vision-tests:0.1.0 apps/detect
```

The test stage has the project's dev tools; the final runtime does not. To update
dependencies, edit only the container project through uv in a compatible
Linux/Python 3.14 development environment, regenerate its lock, rebuild and run
the packaging tests and runtime check. Do not combine `opencv-python` and
`opencv-python-headless` in this environment.
