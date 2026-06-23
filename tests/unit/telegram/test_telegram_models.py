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
