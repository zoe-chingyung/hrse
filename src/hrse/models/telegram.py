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


class TelegramCallbackQuery(BaseModel):
    """A button press on an inline keyboard.

    Reference: https://core.telegram.org/bots/api#callbackquery
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    from_: TelegramUser = Field(..., alias="from")
    message: TelegramMessage | None = None
    data: str | None = None


class TelegramChatMember(BaseModel):
    """Membership state of one user (or the bot) in a chat.

    Only ``status`` is needed; kept as a plain string for forward
    compatibility with statuses Telegram may add.
    """

    model_config = ConfigDict(extra="ignore")

    status: str


class TelegramChatMemberUpdated(BaseModel):
    """The bot's own membership change in a chat (``my_chat_member``).

    Delivered even when group privacy mode is on, which makes it the
    reliable signal that the bot was just added to a group.

    Reference: https://core.telegram.org/bots/api#chatmemberupdated
    """

    model_config = ConfigDict(extra="ignore")

    chat: TelegramChat
    old_chat_member: TelegramChatMember
    new_chat_member: TelegramChatMember


class InlineKeyboardButton(BaseModel):
    """One button of an inline keyboard."""

    text: str
    callback_data: str


class InlineKeyboardMarkup(BaseModel):
    """Inline keyboard attached to a message via ``reply_markup``."""

    inline_keyboard: list[list[InlineKeyboardButton]]


class TelegramUpdate(BaseModel):
    """Top-level Telegram Update object delivered to the webhook.

    Defined after its component models so all references resolve at class
    construction time.

    Reference: https://core.telegram.org/bots/api#update
    """

    model_config = ConfigDict(extra="ignore")

    update_id: int
    message: TelegramMessage | None = None
    callback_query: TelegramCallbackQuery | None = None
    my_chat_member: TelegramChatMemberUpdated | None = None


class SendMessageRequest(BaseModel):
    """Payload sent to the Telegram ``sendMessage`` endpoint."""

    chat_id: int
    text: str
    parse_mode: str = "HTML"
