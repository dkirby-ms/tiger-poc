# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim@sha256:7cf77f594be8042dab6daa9fe326f90962252268b4f120a7f5dccce4d947e6c1 AS dependencies
WORKDIR /app
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-cache

FROM dependencies AS test
RUN uv sync --locked --no-install-project --no-cache
COPY src ./src
COPY tests ./tests
RUN uv run --no-sync ruff check src tests \
    && uv run --no-sync pytest -q --basetemp=/app/.pytest-work

FROM python:3.14-slim-bookworm@sha256:9ab8d9c8514b44f90cf0029dd42fdd7e9e211e639c8b995304cc04568dee900f AS runtime
RUN groupadd --gid 10002 brain \
    && useradd --uid 10002 --gid brain --no-create-home brain
WORKDIR /app
COPY --from=dependencies /app/.venv /app/.venv
COPY src/brain.py ./
ENV PATH="/app/.venv/bin:$PATH" VIRTUAL_ENV=/app/.venv \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10002:10002
STOPSIGNAL SIGTERM
ENTRYPOINT ["python", "/app/brain.py"]
