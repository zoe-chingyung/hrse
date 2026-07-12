"""AWS Secrets Manager providers for Telegram credentials.

Separating credential retrieval from the HTTP client keeps each class focused
and makes it trivial to swap the provider in tests or swap the secret
backend in future sprints (e.g., Parameter Store).

Secret format expected in Secrets Manager
------------------------------------------
Secret name : ``hrse/dev/telegram``  (configurable via ``HRSE_TELEGRAM_SECRET_NAME``)
Region      : ``eu-west-2``
Content     : JSON string  ``{"bot_token": "<token>", "chat_id": "<chat_id>", "chat_ids": ["<id1>", "<id2>"]}``

``chat_ids`` is the preferred multi-chat field used by the schedule handler to
fan out notifications. ``chat_id`` is kept for backward compatibility and is
still used as a fallback when ``chat_ids`` is absent.

Both ``SecretsManagerTokenProvider`` and ``ChatIdProvider`` read the same
secret; the value is fetched once and cached for the Lambda container lifetime.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import lru_cache

import boto3
from aws_lambda_powertools import Logger

logger = Logger(child=True)

# Type alias: any zero-argument callable returning a str token.
BotTokenProvider = Callable[[], str]


class SecretsManagerTokenProvider:
    """Fetches and caches the Telegram bot token from AWS Secrets Manager.

    The token is retrieved lazily on first invocation and then cached for the
    lifetime of the Lambda container. A warm Lambda reuses the cached value
    without incurring an additional Secrets Manager API call.

    Args:
        secret_name: The name (or ARN) of the secret in Secrets Manager.
        region_name: The AWS region where the secret lives.
    """

    def __init__(self, secret_name: str, region_name: str = "eu-west-2") -> None:
        self._secret_name = secret_name
        self._region_name = region_name
        self._cached_token: str | None = None

    def __call__(self) -> str:
        """Return the bot token, fetching from Secrets Manager if not cached."""
        if self._cached_token is None:
            self._cached_token = self._fetch_token()
        return self._cached_token

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_token(self) -> str:
        """Retrieve the secret value and extract ``bot_token``.

        Raises:
            KeyError:  If the secret JSON does not contain ``bot_token``.
            ValueError: If the secret value is not valid JSON.
            botocore.exceptions.ClientError: Propagated from boto3 on AWS errors
                (e.g., secret not found, permission denied).
        """
        logger.info(
            "Fetching Telegram bot token from Secrets Manager",
            extra={"secret_name": self._secret_name, "region": self._region_name},
        )
        client = boto3.client("secretsmanager", region_name=self._region_name)
        response = client.get_secret_value(SecretId=self._secret_name)
        secret_string: str = response["SecretString"]

        try:
            payload: dict[str, str] = json.loads(secret_string)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Secret '{self._secret_name}' is not valid JSON") from exc

        if "bot_token" not in payload:
            raise KeyError(f"Secret '{self._secret_name}' JSON does not contain 'bot_token' key")

        logger.info("Telegram bot token retrieved successfully")
        return payload["bot_token"]


# ---------------------------------------------------------------------------
# Chat ID provider
# ---------------------------------------------------------------------------


# Type alias: any zero-argument callable returning an int chat ID.
ChatIdProvider = Callable[[], int]


class SecretsManagerChatIdProvider:
    """Fetches and caches the Telegram chat ID from AWS Secrets Manager.

    Reads the same secret as ``SecretsManagerTokenProvider``; the chat ID is
    stored under the ``chat_id`` key alongside ``bot_token``.

    Args:
        secret_name: The name (or ARN) of the secret in Secrets Manager.
        region_name: The AWS region where the secret lives.
    """

    def __init__(self, secret_name: str, region_name: str = "eu-west-2") -> None:
        self._secret_name = secret_name
        self._region_name = region_name
        self._cached_chat_id: int | None = None

    def __call__(self) -> int:
        """Return the chat ID, fetching from Secrets Manager if not cached."""
        if self._cached_chat_id is None:
            self._cached_chat_id = self._fetch_chat_id()
        return self._cached_chat_id

    def _fetch_chat_id(self) -> int:
        """Retrieve the secret value and extract ``chat_id``.

        Raises:
            KeyError:   If the secret JSON does not contain ``chat_id``.
            ValueError: If the secret value is not valid JSON or chat_id is not
                        a valid integer.
            botocore.exceptions.ClientError: Propagated from boto3 on AWS errors.
        """
        logger.info(
            "Fetching Telegram chat ID from Secrets Manager",
            extra={"secret_name": self._secret_name, "region": self._region_name},
        )
        client = boto3.client("secretsmanager", region_name=self._region_name)
        response = client.get_secret_value(SecretId=self._secret_name)
        secret_string: str = response["SecretString"]

        try:
            payload: dict[str, str] = json.loads(secret_string)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Secret '{self._secret_name}' is not valid JSON") from exc

        if "chat_id" not in payload:
            raise KeyError(f"Secret '{self._secret_name}' JSON does not contain 'chat_id' key")

        try:
            chat_id = int(payload["chat_id"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Secret '{self._secret_name}' chat_id is not a valid integer"
            ) from exc

        logger.info("Telegram chat ID retrieved successfully")
        return chat_id


@lru_cache(maxsize=1)
def get_chat_id_provider() -> SecretsManagerChatIdProvider:
    """Return a cached ``SecretsManagerChatIdProvider`` wired from settings.

    Call ``get_chat_id_provider.cache_clear()`` in tests to reset.
    """
    from hrse.config import get_settings

    settings = get_settings()
    return SecretsManagerChatIdProvider(
        secret_name=settings.telegram_secret_name,
        region_name="eu-west-2",
    )


# ---------------------------------------------------------------------------
# Multi-chat IDs provider
# ---------------------------------------------------------------------------

# Type alias: any zero-argument callable returning a list of int chat IDs.
ChatIdsProvider = Callable[[], list[int]]


class SecretsManagerChatIdsProvider:
    """Fetches and caches the list of Telegram chat IDs from AWS Secrets Manager.

    Reads the ``chat_ids`` key (list of IDs) from the secret when present.
    Falls back to the singular ``chat_id`` key so that existing secrets work
    without migration.

    Args:
        secret_name: The name (or ARN) of the secret in Secrets Manager.
        region_name: The AWS region where the secret lives.
    """

    def __init__(self, secret_name: str, region_name: str = "eu-west-2") -> None:
        self._secret_name = secret_name
        self._region_name = region_name
        self._cached: list[int] | None = None

    def __call__(self) -> list[int]:
        """Return all chat IDs, fetching from Secrets Manager if not cached."""
        if self._cached is None:
            self._cached = self._fetch_chat_ids()
        return self._cached

    def _fetch_chat_ids(self) -> list[int]:
        """Retrieve the secret value and extract chat IDs.

        Prefers the ``chat_ids`` list; falls back to the singular ``chat_id``
        for backward compatibility.

        Raises:
            KeyError:   If neither ``chat_ids`` nor ``chat_id`` is present.
            ValueError: If the secret is not valid JSON or an ID is not a valid int.
            botocore.exceptions.ClientError: Propagated from boto3 on AWS errors.
        """
        logger.info(
            "Fetching Telegram chat IDs from Secrets Manager",
            extra={"secret_name": self._secret_name, "region": self._region_name},
        )
        client = boto3.client("secretsmanager", region_name=self._region_name)
        response = client.get_secret_value(SecretId=self._secret_name)
        secret_string: str = response["SecretString"]

        try:
            payload: dict[str, object] = json.loads(secret_string)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Secret '{self._secret_name}' is not valid JSON") from exc

        if "chat_ids" in payload:
            raw_ids = payload["chat_ids"]
            if not isinstance(raw_ids, list):
                raise ValueError(f"Secret '{self._secret_name}' chat_ids must be a JSON array")
            try:
                ids = [int(str(cid)) for cid in raw_ids]
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Secret '{self._secret_name}' chat_ids contains a non-integer value"
                ) from exc
        elif "chat_id" in payload:
            try:
                ids = [int(str(payload["chat_id"]))]
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Secret '{self._secret_name}' chat_id is not a valid integer"
                ) from exc
        else:
            raise KeyError(
                f"Secret '{self._secret_name}' JSON contains neither 'chat_ids' nor 'chat_id'"
            )

        logger.info("Telegram chat IDs retrieved successfully", extra={"count": len(ids)})
        return ids


@lru_cache(maxsize=1)
def get_chat_ids_provider() -> SecretsManagerChatIdsProvider:
    """Return a cached ``SecretsManagerChatIdsProvider`` wired from settings.

    Call ``get_chat_ids_provider.cache_clear()`` in tests to reset.
    """
    from hrse.config import get_settings

    settings = get_settings()
    return SecretsManagerChatIdsProvider(
        secret_name=settings.telegram_secret_name,
        region_name="eu-west-2",
    )
