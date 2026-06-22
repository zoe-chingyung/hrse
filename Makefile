# Convenience targets. All commands run inside the uv-managed venv.
.PHONY: install lint fmt typecheck test test-unit test-integration clean build-lambda

install:
	uv sync --extra dev

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

# Build a Lambda-ready ZIP (install deps into a staging dir, then zip with src)
build-lambda:
	rm -rf lambda_packages/hrse
	mkdir -p lambda_packages/hrse
	uv pip install --target lambda_packages/hrse --python-platform linux .
	cd lambda_packages && zip -r hrse.zip hrse/

clean:
	rm -rf lambda_packages/ .venv/ .mypy_cache/ .ruff_cache/ .pytest_cache/ \
	       coverage.xml htmlcov/ dist/ build/ src/hrse.egg-info/
