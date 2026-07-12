"""Per-chat settings store — Protocol and S3 implementation.

Storage layout
--------------
Bucket  : the existing state bucket (``HRSE_STATE_BUCKET_NAME``)
Key     : ``settings/{chat_id}.json``  (one object per chat)
Format  : JSON-serialised ``ChatSettings``.

One object per chat avoids the read-modify-write contention risk noted for
the shared events file: two chats configuring simultaneously never touch the
same key.

Replacing this backend
----------------------
Swap ``S3ChatSettingsStore`` for any class satisfying ``ChatSettingsStore``
at the factory level (``get_chat_settings_store``). Nothing else changes.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol, runtime_checkable

import boto3
from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError

from hrse.models.chat_settings import ChatSettings

logger = Logger(child=True)

_SETTINGS_PREFIX = "settings/"


@runtime_checkable
class ChatSettingsStore(Protocol):
    """Structural contract for per-chat settings persistence."""

    def get(self, chat_id: int) -> ChatSettings | None:
        """Return the settings for ``chat_id``, or None if never configured.

        Args:
            chat_id: Telegram chat identifier.

        Returns:
            The stored ``ChatSettings`` or ``None``.
        """
        ...

    def save(self, settings: ChatSettings) -> None:
        """Persist ``settings``, overwriting any previous value for the chat.

        Args:
            settings: The settings to store.
        """
        ...


class S3ChatSettingsStore:
    """Stores one ``ChatSettings`` JSON object per chat in S3.

    Args:
        bucket_name: The S3 bucket to read from and write to.
        region_name: AWS region of the bucket.
    """

    def __init__(self, bucket_name: str, region_name: str = "eu-west-2") -> None:
        self._bucket = bucket_name
        self._client = boto3.client("s3", region_name=region_name)

    # ------------------------------------------------------------------
    # ChatSettingsStore implementation
    # ------------------------------------------------------------------

    def get(self, chat_id: int) -> ChatSettings | None:
        """Download and validate the settings object for ``chat_id``.

        Args:
            chat_id: Telegram chat identifier.

        Returns:
            ``ChatSettings`` or ``None`` when the chat has no stored settings.
        """
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=_key(chat_id))
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "NoSuchKey":
                logger.debug("No settings for chat", extra={"chat_id": chat_id})
                return None
            raise
        return ChatSettings.model_validate_json(response["Body"].read())

    def save(self, settings: ChatSettings) -> None:
        """Serialise and upload ``settings`` to S3.

        Args:
            settings: The settings to persist.
        """
        body = settings.model_dump_json(indent=2).encode()
        self._client.put_object(
            Bucket=self._bucket,
            Key=_key(settings.chat_id),
            Body=body,
            ContentType="application/json",
        )
        logger.info(
            "Chat settings saved",
            extra={"chat_id": settings.chat_id, "language": settings.language},
        )


class InMemoryChatSettingsStore:
    """Dict-backed store for tests and local development."""

    def __init__(self) -> None:
        self._data: dict[int, ChatSettings] = {}

    def get(self, chat_id: int) -> ChatSettings | None:
        """Return stored settings for ``chat_id`` or ``None``."""
        return self._data.get(chat_id)

    def save(self, settings: ChatSettings) -> None:
        """Store ``settings`` keyed by chat id."""
        self._data[settings.chat_id] = settings


# ---------------------------------------------------------------------------
# Private helpers / factory
# ---------------------------------------------------------------------------


def _key(chat_id: int) -> str:
    """Return the S3 object key for ``chat_id``."""
    return f"{_SETTINGS_PREFIX}{chat_id}.json"


@lru_cache(maxsize=1)
def get_chat_settings_store() -> S3ChatSettingsStore:
    """Return a cached ``S3ChatSettingsStore`` wired from application settings.

    Called once per Lambda container lifetime.
    Call ``get_chat_settings_store.cache_clear()`` in tests to reset.
    """
    from hrse.config import get_settings

    settings = get_settings()
    return S3ChatSettingsStore(
        bucket_name=settings.state_bucket_name,
        region_name=settings.aws_region,
    )
