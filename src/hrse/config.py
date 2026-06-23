"""Runtime configuration loaded from environment variables.

All settings are read once at cold-start and cached. Use Pydantic's
BaseSettings so that values can be overridden in tests via env vars or
monkeypatching.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Top-level application settings.

    Values are sourced (in order of precedence):
    1. Explicit keyword arguments passed to Settings()
    2. Environment variables
    3. .env file (only in local development, not in Lambda)
    4. Default values defined here
    """

    model_config = SettingsConfigDict(
        env_prefix="HRSE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # AWS region where resources live
    aws_region: str = Field(default="eu-west-2", description="AWS region")

    # DynamoDB table name for schedule state
    schedule_table_name: str = Field(
        default="hrse-schedules",
        description="DynamoDB table for schedule persistence",
    )

    # Log level forwarded to Lambda Powertools logger
    log_level: str = Field(default="INFO", description="Log level (DEBUG|INFO|WARNING|ERROR)")

    # AWS Secrets Manager secret name holding the Telegram bot token.
    # Secret content must be JSON: {"bot_token": "<token>"}
    telegram_secret_name: str = Field(
        default="hrse/dev/telegram",
        description="Secrets Manager secret name for Telegram credentials",
    )

    # S3 bucket used to persist household activity events.
    # Bucket is created by Terraform; name follows the pattern hrse-{env}-state.
    state_bucket_name: str = Field(
        default="hrse-dev-state",
        description="S3 bucket name for household event storage",
    )

    # Feature flag: enable experimental optimiser (Sprint 3+)
    enable_optimiser: bool = Field(default=False, description="Enable experimental optimiser")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton.

    Call ``get_settings.cache_clear()`` in tests to force re-initialisation.
    """
    return Settings()
