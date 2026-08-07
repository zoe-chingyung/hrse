"""Unit tests for the read-only /tasks command.

Sprint C retired /add_task and /remove_task — task selection now happens
once via the button multi-select picker during onboarding; changing it
means /reset.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from hrse.models.chat_settings import ChatSettings, Language
from hrse.store.chat_settings_store import InMemoryChatSettingsStore
from hrse.telegram.commands import handle_tasks
from hrse.utils.datetime_utils import utcnow

_CHAT = -100123


def _mock_client() -> MagicMock:
    return MagicMock()


class TestHandleTasks:
    def test_no_stored_settings_prompts_setup(self) -> None:
        client = _mock_client()
        handle_tasks(
            chat_id=_CHAT,
            client=client,
            settings_store=InMemoryChatSettingsStore(),
            lang=Language.EN,
        )
        _, kwargs = client.send_message.call_args
        assert "no tasks configured" in kwargs["text"].lower()

    def test_lists_every_enabled_task(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(
            ChatSettings(
                chat_id=_CHAT, enabled_tasks=["laundry", "dishwasher"], updated_at=utcnow()
            )
        )
        client = _mock_client()
        handle_tasks(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)
        _, kwargs = client.send_message.call_args
        assert "Laundry" in kwargs["text"]
        assert "Dishwasher" in kwargs["text"]

    def test_zh_variant_differs(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(ChatSettings(chat_id=_CHAT, enabled_tasks=["laundry"], updated_at=utcnow()))
        client = _mock_client()
        handle_tasks(chat_id=_CHAT, client=client, settings_store=store, lang=Language.ZH)
        _, kwargs = client.send_message.call_args
        assert "你已啟用嘅任務" in kwargs["text"]

    def test_empty_enabled_tasks_prompts_setup(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(ChatSettings(chat_id=_CHAT, enabled_tasks=[], updated_at=utcnow()))
        client = _mock_client()
        handle_tasks(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)
        _, kwargs = client.send_message.call_args
        assert "no tasks configured" in kwargs["text"].lower()
