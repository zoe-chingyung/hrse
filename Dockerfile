# HRSE — Development image
#
# Used for: running tests, linting, mypy, and demo.py locally.
# NOT used for Lambda deployment (see Dockerfile.lambda for that).
#
# Usage:
#   docker compose run --rm test
#   docker compose run --rm lint
#   docker compose run --rm demo

FROM python:3.12-slim

# System deps — git for pre-commit
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifests first (better layer caching —
# only reruns on pyproject.toml / uv.lock changes)
COPY pyproject.toml uv.lock README.md ./

# Install all deps including dev
RUN uv sync --extra dev --frozen

# Copy source
COPY src/ src/
COPY tests/ tests/
COPY demo.py mock_server.py ./

# Default: run the full test suite
CMD ["uv", "run", "pytest"]
