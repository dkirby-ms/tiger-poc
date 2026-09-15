# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim@sha256:7cf77f594be8042dab6daa9fe326f90962252268b4f120a7f5dccce4d947e6c1 AS dependencies
WORKDIR /app
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-cache

FROM dependencies AS test
RUN apt-get update && apt-get install --no-install-recommends -y libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* && mkdir /app/runtime
ENV HOME=/app/runtime YOLO_CONFIG_DIR=/app/runtime MPLCONFIGDIR=/app/runtime/matplotlib
RUN uv sync --locked --no-install-project --no-cache
COPY src/entrypoint.py src/package_detector.py src/observation_service.py ./src/
COPY tests ./tests
RUN --mount=type=bind,source=src/rtsp_yolo.py,target=/app/src/rtsp_yolo.py \
    uv run --no-sync ruff check src/entrypoint.py src/package_detector.py src/observation_service.py tests \
    && uv run --no-sync pytest -q --basetemp=/app/.pytest-work

FROM dependencies AS source
COPY src/package_detector.py /app/package_detector.py
RUN --mount=type=bind,source=src/rtsp_yolo.py,target=/source/rtsp_yolo.py \
    mkdir /packaged && uv run --no-sync python package_detector.py

FROM python:3.14-slim-bookworm@sha256:9ab8d9c8514b44f90cf0029dd42fdd7e9e211e639c8b995304cc04568dee900f AS runtime
RUN apt-get update \
    && apt-get install --no-install-recommends -y libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 vision \
    && useradd --uid 10001 --gid vision --no-create-home vision \
    && mkdir /output /models \
    && chown vision:vision /output
WORKDIR /app
COPY --from=dependencies /app/.venv /app/.venv
COPY --from=source /packaged/rtsp_yolo.py ./
COPY src/entrypoint.py src/observation_service.py ./
ENV PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV=/app/.venv \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/app/runtime \
    TMPDIR=/app/runtime \
    YOLO_CONFIG_DIR=/app/runtime \
    MPLCONFIGDIR=/app/runtime/matplotlib \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    YOLO_AUTOINSTALL=false \
    YOLO_OFFLINE=true \
    OPENCV_LOG_LEVEL=SILENT \
    OPENCV_FFMPEG_LOGLEVEL=-8 \
    OPENCV_FFMPEG_CAPTURE_OPTIONS="rtsp_transport;tcp"
USER 10001:10001
STOPSIGNAL SIGTERM
ENTRYPOINT ["python", "/app/entrypoint.py"]
