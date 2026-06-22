"""AWS Secrets Manager token provider for the Telegram bot token.

Separating token retrieval from the HTTP client keeps each class focused
and makes it trivial to swap the provider in tests or swap the secret
backend in future sprints (e.g., Parameter Store).

Secret format expected in Secrets Manager
------------------------------------------
Secret name : ``hrse/dev/telegram``  (configurable via ``HRSE_TELEGRAM_SECRET_NAME``)
Region      : ``eu-west-2``
Content     : JSON string  ``{"bot_token": "<token>"}``
"""

from __future__ import annotations

import json
from typing import Callable

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
            raise ValueError(
                f"Secret '{self._secret_name}' is not valid JSON"
            ) from exc

        if "bot_token" not in payload:
            raise KeyError(
                f"Secret '{self._secret_name}' JSON does not contain 'bot_token' key"
            )

        logger.info("Telegram bot token retrieved successfully")
        return payload["bot_token"]
