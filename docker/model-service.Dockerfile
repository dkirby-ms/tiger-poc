FROM python:3.11-slim

WORKDIR /app

COPY apps/__init__.py apps/__init__.py
COPY apps/local_model_runtime apps/local_model_runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MODEL_SERVICE_CATALOG=/app/models/services.json

RUN useradd --create-home --uid 10001 modelservice
USER modelservice

ENTRYPOINT ["python", "-m", "apps.local_model_runtime"]
