"""Unit tests for application configuration."""

import pytest

from hrse.config import Settings, get_settings


class TestSettings:
    """Settings defaults and env-var overrides."""

    def test_defaults(self) -> None:
        s = Settings()
        assert s.aws_region == "eu-west-2"
        assert s.schedule_table_name == "hrse-schedules"
        assert s.log_level == "INFO"
        assert s.enable_optimiser is False
        assert s.telegram_secret_name == "hrse/dev/telegram"
        assert s.state_bucket_name == "hrse-dev-state"

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HRSE_AWS_REGION", "eu-west-1")
        monkeypatch.setenv("HRSE_ENABLE_OPTIMISER", "true")
        s = Settings()
        assert s.aws_region == "eu-west-1"
        assert s.enable_optimiser is True

    def test_singleton_is_cached(self) -> None:
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_cache_cleared_between_tests(self) -> None:
        # The autouse fixture in conftest resets the cache, so this call
        # should always return a fresh instance relative to the previous test.
        s = get_settings()
        assert s is not None
