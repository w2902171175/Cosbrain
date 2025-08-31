# syntax=docker/dockerfile:1

FROM python:3.10-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PRODUCTION=true

WORKDIR /app

# OS deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc g++ \
    curl git \
    libpq-dev \
    libgomp1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifests first for caching
COPY requirements.txt ./

# Install Python deps
RUN python -m pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy application code
COPY . .

# Copy entrypoint and make executable
COPY docker/docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8001

ENV HOST=0.0.0.0 \
    PORT=8001

ENTRYPOINT ["/bin/sh", "-c", "/entrypoint.sh"]
