# syntax=docker/dockerfile:1.6
# TTS API — CUDA-enabled runtime image.
# Base matches the plan: CUDA 12.1 runtime on Ubuntu 22.04.
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models_cache/huggingface \
    TRANSFORMERS_CACHE=/models_cache/huggingface

# System deps: Python 3.11, audio libs, build tools for any wheels that need them.
RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common \
        curl \
        ca-certificates \
        git \
        ffmpeg \
        libsndfile1 \
        libopus0 \
        libopus-dev \
        build-essential \
    && add-apt-repository ppa:deadsnakes/ppa -y \
    && apt-get update && apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-dev \
        python3.11-venv \
        python3-pip \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && rm -rf /var/lib/apt/lists/*

# Install torch first from CUDA index so we pull the CUDA 12.1 build, then everything else.
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install --index-url https://download.pytorch.org/whl/cu121 torch==2.4.1 \
    && python -m pip install -r requirements.txt

# App code
COPY app/ ./app/
COPY benchmark/ ./benchmark/

# Model cache lives on a mounted volume so restarts don't re-download weights.
RUN mkdir -p /models_cache/huggingface

EXPOSE 8000

# Healthcheck hits the API's own /health endpoint.
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
