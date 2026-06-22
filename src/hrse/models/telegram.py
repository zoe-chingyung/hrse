"""Pydantic models for the Telegram Bot API update payload.

Only the fields HRSE needs are declared. Extra fields sent by Telegram
are silently ignored (``model_config = ConfigDict(extra="ignore")``).

Reference: https://core.telegram.org/bots/api#update
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TelegramChat(BaseModel):
    """Minimal representation of a Telegram chat."""

    model_config = ConfigDict(extra="ignore")

    id: int


class TelegramUser(BaseModel):
    """Minimal representation of a Telegram user."""

    model_config = ConfigDict(extra="ignore")

    id: int
    is_bot: bool = False
    first_name: str = ""
    username: str | None = None


class TelegramMessage(BaseModel):
    """Minimal representation of a Telegram message."""

    model_config = ConfigDict(extra="ignore")

    message_id: int
    chat: TelegramChat
    from_: TelegramUser | None = Field(None, alias="from")
    text: str | None = None


class TelegramUpdate(BaseModel):
    """Top-level Telegram Update object delivered to the webhook.

    Reference: https://core.telegram.org/bots/api#update
    """

    model_config = ConfigDict(extra="ignore")

    update_id: int
    message: TelegramMessage | None = None


class SendMessageRequest(BaseModel):
    """Payload sent to the Telegram ``sendMessage`` endpoint."""

    chat_id: int
    text: str
    parse_mode: str = "HTML"
