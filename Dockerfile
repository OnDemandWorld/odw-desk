# Multi-stage Dockerfile for ODW.ai Desk
# Production-ready with optimized layers

# Stage 1: Builder
FROM python:3.14-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies in virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Audit #63: bake the spaCy NER model into the image — Presidio otherwise
# downloads ~560MB at first use, which fails outright in air-gapped
# deployments (the sovereignty-focused target market) and crash-loops the
# AI worker.
RUN python -m spacy download en_core_web_lg

# Stage 2: Production
FROM python:3.14-slim as production

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash desk

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH=/app/src

# Copy application code
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY pyproject.toml .

# Set ownership
RUN chown -R desk:desk /app

# Switch to non-root user
USER desk

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run application.
# Single worker: webchat/agent WebSocket registries and runtime-settings
# overrides are process-local, and each worker would start its own message
# processor/SLA scanner. Scaling beyond 1 worker/replica requires a Redis
# pub/sub delivery relay and a shared override cache first (audit #9).
CMD ["uvicorn", "desk.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
