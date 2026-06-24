# HRSE — Development image
#
# Used for: running tests, linting, mypy, and demo.py locally.
# NOT used for Lambda deployment (see Dockerfile.lambda for that).
#
# Usage:
#   docker build -t hrse-dev .
#   docker run --rm hrse-dev pytest
#   docker run --rm --env-file .env hrse-dev python demo.py

FROM python:3.12-slim

# System deps — curl for healthchecks, git for pre-commit
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl git \
    && rm -rf /var/lib/apt/lists/*

# Install uv — fast Python package manager
COPY --from=ghcr.io/astral-sh/uv:0.2.33 /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifests first (better layer caching)
COPY pyproject.toml uv.lock ./

# Install all deps including dev (cached layer — only reruns on pyproject.toml change)
RUN uv sync --extra dev --frozen

# Copy source
COPY src/ src/
COPY tests/ tests/
COPY demo.py mock_server.py ./

# Install the hrse package itself in editable mode
RUN uv pip install -e . --no-deps

# Default: run the full test suite
CMD ["uv", "run", "pytest"]
