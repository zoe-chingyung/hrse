# Convenience targets. All commands run inside the uv-managed venv.
.PHONY: install install-hooks lint fmt fmt-check typecheck test test-unit \
				test-integration check clean build-lambda

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

install:
	uv sync --extra dev

# Install pre-commit hooks into .git/hooks — run once after cloning.
install-hooks: install
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push

# ---------------------------------------------------------------------------
# Individual checks (also called by pre-commit and CI)
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

# ---------------------------------------------------------------------------
# Full pre-push gate — mirrors CI and pre-commit in one command.
# Run this before pushing to main if you want to be sure.
#   make check
# ---------------------------------------------------------------------------

check: fmt lint typecheck test

# ---------------------------------------------------------------------------
# Build / clean
# ---------------------------------------------------------------------------

# Build a Lambda-ready ZIP (install deps into a staging dir, then zip with src)
build-lambda:
	rm -rf lambda_packages/hrse
	mkdir -p lambda_packages/hrse
	uv pip install --target lambda_packages/hrse --python-platform linux .
# 	uv run python -c "import shutil; shutil.make_archive('lambda_packages/hrse', 'zip', 'lambda_packages/hrse')"
	cd lambda_packages && zip -r hrse.zip hrse/

clean:
	rm -rf lambda_packages/ .venv/ .mypy_cache/ .ruff_cache/ .pytest_cache/ \
				 coverage.xml htmlcov/ dist/ build/ src/hrse.egg-info/
