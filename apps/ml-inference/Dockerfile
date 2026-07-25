# syntax=docker/dockerfile:1.7

# ---------- Builder stage ----------
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment using standard python venv
# (uv venv creation fails on some platforms; pip is universally reliable)
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml ./
COPY krishisetu_ml/ ./krishisetu_ml/

# Install dependencies into the virtual env using standard pip
RUN pip install --no-cache-dir .


# ---------- Runtime stage ----------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 krishisetu

WORKDIR /app

COPY --from=builder --chown=krishisetu:krishisetu /opt/venv /opt/venv
COPY --chown=krishisetu:krishisetu . .

# Create models directory for mounted model files
RUN mkdir -p /app/models && chown krishisetu:krishisetu /app/models

USER krishisetu

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8001/health || exit 1

CMD ["uvicorn", "krishisetu_ml.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8001", \
     "--workers", "1", \
     "--timeout-keep-alive", "5"]
