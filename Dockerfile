# syntax=docker/dockerfile:1

# Builder stage - install UV and dependencies
FROM python:3.12-slim AS builder

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files and README (required by pyproject.toml)
COPY pyproject.toml uv.lock README.md ./

# Install dependencies into a virtual environment
RUN uv sync --frozen --no-dev

# Copy application source
COPY src ./src

# Runtime stage - minimal dependencies
FROM python:3.12-slim AS runtime

# Install curl for healthcheck
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 1000 pii && \
    useradd -u 1000 -g pii -m -s /bin/bash pii

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=pii:pii /app/.venv /app/.venv

# Copy application source from builder
COPY --from=builder --chown=pii:pii /app/src /app/src

# Set PATH to include virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src:$PYTHONPATH"

# Expose ports
EXPOSE 8000 50051

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Switch to non-root user
USER pii

# Run the application
CMD ["python", "-m", "pii_service.main"]
