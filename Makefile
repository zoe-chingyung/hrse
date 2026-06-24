# HRSE — convenience targets.
# All Python commands run inside the uv-managed virtualenv.
#
# Build + deploy (Git Bash / Linux / macOS):
#   make build-lambda          # build the Lambda package
#   make deploy ENV=dev        # build + terraform apply
#   make plan   ENV=dev        # build + terraform plan
#
# On Windows, run the shell commands directly in Git Bash — see README.md.

.PHONY: install install-hooks lint fmt fmt-check typecheck test test-unit \
        test-integration check clean build-lambda deploy plan

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

install:
	uv sync --extra dev

install-hooks: install
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push

# ---------------------------------------------------------------------------
# Quality checks (mirrored in CI and pre-commit)
# ---------------------------------------------------------------------------

lint:
	uv run ruff check .

fmt:
	uv run ruff format .

fmt-check:
	uv run ruff format --check .

typecheck:
	uv run mypy

test:
	uv run pytest

test-unit:
	uv run pytest -m unit

test-integration:
	uv run pytest -m integration

# Run the full quality gate locally — same as CI.
check: fmt lint typecheck test

# ---------------------------------------------------------------------------
# Lambda build
#
# Installs the hrse package + all pinned runtime deps into lambda_packages/hrse/
# using Linux/Python 3.12 wheels (correct for the Lambda runtime regardless of
# host OS). Terraform's archive_file then zips that directory on apply and
# uploads only when the content hash changes.
#
# Two-pass install:
#   Pass 1 — export exact pinned deps from uv.lock → requirements.txt
#   Pass 2 — install deps into target dir with Linux wheels
#   Pass 3 — install hrse package itself (--no-deps, already resolved above)
# ---------------------------------------------------------------------------

build-lambda:
	rm -rf lambda_packages/hrse lambda_packages/_reqs.txt
	mkdir -p lambda_packages/hrse
	uv export --no-dev --no-emit-project --no-hashes \
		--format requirements-txt \
		--output-file lambda_packages/_reqs.txt
	uv pip install \
		--target lambda_packages/hrse \
		--python-platform linux \
		--python-version 3.12 \
		-r lambda_packages/_reqs.txt
	uv pip install \
		--target lambda_packages/hrse \
		--python-platform linux \
		--python-version 3.12 \
		--no-deps \
		.
	rm -f lambda_packages/_reqs.txt
	@echo "Build complete — $$(find lambda_packages/hrse -type f | wc -l) files"

# Deploy: build then terraform apply.
deploy: build-lambda
	cd infra && terraform apply -var environment=$(ENV)

# Plan only — no changes applied.
plan: build-lambda
	cd infra && terraform plan -var environment=$(ENV)

# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------

clean:
	rm -rf lambda_packages/ .venv/ .mypy_cache/ .ruff_cache/ .pytest_cache/ \
	       coverage.xml htmlcov/ dist/ build/ src/hrse.egg-info/

# ---------------------------------------------------------------------------
# Docker targets
# ---------------------------------------------------------------------------

# Build both Docker images
docker-build:
	docker compose build

# Run full test suite inside Docker (no local Python needed)
docker-test:
	docker compose run --rm test

# Lint inside Docker
docker-lint:
	docker compose run --rm lint

# Typecheck inside Docker
docker-typecheck:
	docker compose run --rm typecheck

# Full quality gate inside Docker — mirrors CI
docker-check: docker-lint docker-typecheck docker-test

# Build Lambda package using the Lambda builder image (correct Linux wheels)
# This replaces `make build-lambda` on Windows — use this instead.
docker-build-lambda:
	mkdir -p lambda_packages/hrse
	docker compose run --rm lambda-builder

# Build Lambda package then deploy via Terraform
docker-deploy: docker-build-lambda
	cd infra && terraform apply -var environment=$(ENV)
