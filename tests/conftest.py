"""Root pytest conftest.

Fixtures defined here are available to all test modules.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def reset_settings_cache() -> None:
    """Clear the Settings LRU cache before every test.

    This ensures that environment variable overrides set inside a test
    are picked up by ``get_settings()`` rather than returning a stale
    cached instance.
    """
    from hrse.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def aws_credentials() -> None:
    """Set dummy AWS credentials so moto does not hit real AWS."""
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
    os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
    os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
    os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-2")
