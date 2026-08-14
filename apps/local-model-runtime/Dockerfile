FROM nvidia/cuda:12.8.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --no-install-recommends --yes python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY server.py .

ENV MODEL_BUNDLE_DIR=/models \
    FOUNDRY_EXECUTION_PROVIDER=CUDAExecutionProvider \
    FOUNDRY_RUNTIME_MODE=onnx \
    FOUNDRY_PORT=8000

CMD ["python3", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]

EXPOSE 8000
ENTRYPOINT ["python3", "server.py"]
