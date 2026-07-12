"""Unit tests for Telegram Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hrse.models.telegram import TelegramUpdate


class TestTelegramUpdate:
    def _valid_payload(self) -> dict:
        return {
            "update_id": 123456,
            "message": {
                "message_id": 1,
                "chat": {"id": 999},
                "from": {"id": 42, "is_bot": False, "first_name": "Alice"},
                "text": "/health",
            },
        }

    def test_valid_update_parses(self) -> None:
        u = TelegramUpdate.model_validate(self._valid_payload())
        assert u.update_id == 123456
        assert u.message is not None
        assert u.message.text == "/health"

    def test_extra_fields_ignored(self) -> None:
        payload = self._valid_payload()
        payload["unknown_field"] = "should be ignored"
        u = TelegramUpdate.model_validate(payload)
        assert u.update_id == 123456

    def test_message_is_optional(self) -> None:
        u = TelegramUpdate.model_validate({"update_id": 1})
        assert u.message is None

    def test_missing_update_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            TelegramUpdate.model_validate({"message": {}})

    def test_from_field_alias(self) -> None:
        """'from' is a Python keyword; it must be parsed via alias."""
        payload = self._valid_payload()
        u = TelegramUpdate.model_validate(payload)
        assert u.message is not None
        assert u.message.from_ is not None
        assert u.message.from_.first_name == "Alice"

    def test_text_is_optional(self) -> None:
        payload = self._valid_payload()
        del payload["message"]["text"]
        u = TelegramUpdate.model_validate(payload)
        assert u.message is not None
        assert u.message.text is None


# ---------------------------------------------------------------------------
# Sprint 6 — my_chat_member and callback_query updates
# ---------------------------------------------------------------------------


class TestMyChatMemberUpdate:
    def test_parses_bot_added_to_group(self) -> None:
        payload = {
            "update_id": 900,
            "my_chat_member": {
                "chat": {"id": -100123, "type": "group", "title": "Family"},
                "from": {"id": 42, "is_bot": False, "first_name": "Zoe"},
                "date": 1789000000,
                "old_chat_member": {
                    "user": {"id": 7, "is_bot": True, "first_name": "HRSE"},
                    "status": "left",
                },
                "new_chat_member": {
                    "user": {"id": 7, "is_bot": True, "first_name": "HRSE"},
                    "status": "member",
                },
            },
        }
        update = TelegramUpdate.model_validate(payload)
        assert update.my_chat_member is not None
        assert update.my_chat_member.chat.id == -100123
        assert update.my_chat_member.old_chat_member.status == "left"
        assert update.my_chat_member.new_chat_member.status == "member"
        assert update.message is None


class TestCallbackQueryUpdate:
    def test_parses_language_button_press(self) -> None:
        payload = {
            "update_id": 901,
            "callback_query": {
                "id": "cb-1",
                "from": {"id": 42, "is_bot": False, "first_name": "Zoe"},
                "message": {
                    "message_id": 55,
                    "chat": {"id": -100123, "type": "group"},
                    "date": 1789000000,
                },
                "data": "lang:zh",
            },
        }
        update = TelegramUpdate.model_validate(payload)
        assert update.callback_query is not None
        assert update.callback_query.data == "lang:zh"
        assert update.callback_query.message is not None
        assert update.callback_query.message.chat.id == -100123

    def test_callback_without_message_parses(self) -> None:
        payload = {
            "update_id": 902,
            "callback_query": {
                "id": "cb-2",
                "from": {"id": 42, "is_bot": False, "first_name": "Zoe"},
                "data": "lang:en",
            },
        }
        update = TelegramUpdate.model_validate(payload)
        assert update.callback_query is not None
        assert update.callback_query.message is None


class TestInlineKeyboardModels:
    def test_markup_dumps_to_telegram_shape(self) -> None:
        from hrse.models.telegram import InlineKeyboardButton, InlineKeyboardMarkup

        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="English", callback_data="lang:en")]]
        )
        assert markup.model_dump() == {
            "inline_keyboard": [[{"text": "English", "callback_data": "lang:en"}]]
        }
