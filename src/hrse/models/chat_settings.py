"""Domain models for per-chat settings.

Sprint 6 — Group onboarding & language.

Each Telegram chat (private or group) can carry its own settings. The first
setting is the display language, chosen via the onboarding inline keyboard.
Future sprints will extend this model with per-chat task configuration.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TCH003 — used as Pydantic field type at runtime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Language(StrEnum):
    """Supported display languages.

    Values double as the suffix of the ``lang:*`` callback data sent by the
    onboarding inline keyboard.
    """

    EN = "en"
    ZH = "zh"


class ChatSettings(BaseModel):
    """Settings for a single Telegram chat.

    Attributes:
        chat_id:    Telegram chat identifier. Negative for groups.
        language:   Display language for bot replies in this chat.
        updated_at: UTC timestamp of the last settings change.
    """

    model_config = ConfigDict(frozen=True)

    chat_id: int = Field(..., description="Telegram chat identifier (negative for groups)")
    language: Language = Field(default=Language.EN, description="Display language")
    updated_at: datetime = Field(..., description="UTC timestamp of last update")
