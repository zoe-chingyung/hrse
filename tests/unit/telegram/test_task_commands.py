"""Unit tests for the Sprint 5C /tasks, /add_task, /remove_task commands."""

from __future__ import annotations

from unittest.mock import MagicMock

from hrse.models.chat_settings import ChatSettings, Language
from hrse.store.chat_settings_store import InMemoryChatSettingsStore
from hrse.telegram.commands import handle_add_task, handle_remove_task, handle_tasks
from hrse.utils.datetime_utils import utcnow

_CHAT = -100123


def _mock_client() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# handle_tasks
# ---------------------------------------------------------------------------


class TestHandleTasks:
    def test_no_stored_settings_defaults_to_laundry(self) -> None:
        client = _mock_client()
        handle_tasks(
            chat_id=_CHAT,
            client=client,
            settings_store=InMemoryChatSettingsStore(),
            lang=Language.EN,
        )
        _, kwargs = client.send_message.call_args
        assert "Laundry" in kwargs["text"]

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
        client = _mock_client()
        handle_tasks(
            chat_id=_CHAT,
            client=client,
            settings_store=InMemoryChatSettingsStore(),
            lang=Language.ZH,
        )
        _, kwargs = client.send_message.call_args
        assert "你已啟用嘅任務" in kwargs["text"]


# ---------------------------------------------------------------------------
# handle_add_task
# ---------------------------------------------------------------------------


class TestHandleAddTask:
    def test_no_args_sends_usage(self) -> None:
        client = _mock_client()
        handle_add_task(
            chat_id=_CHAT,
            args=[],
            client=client,
            settings_store=InMemoryChatSettingsStore(),
            lang=Language.EN,
        )
        _, kwargs = client.send_message.call_args
        assert "Usage" in kwargs["text"]

    def test_unknown_task_sends_error_with_valid_list(self) -> None:
        client = _mock_client()
        handle_add_task(
            chat_id=_CHAT,
            args=["gardening"],
            client=client,
            settings_store=InMemoryChatSettingsStore(),
            lang=Language.EN,
        )
        _, kwargs = client.send_message.call_args
        assert "gardening" in kwargs["text"]
        assert "laundry" in kwargs["text"]

    def test_adds_new_task_to_defaults(self) -> None:
        store = InMemoryChatSettingsStore()
        handle_add_task(
            chat_id=_CHAT,
            args=["dishwasher"],
            client=_mock_client(),
            settings_store=store,
            lang=Language.EN,
        )
        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.enabled_tasks == ["laundry", "dishwasher"]

    def test_add_is_case_insensitive(self) -> None:
        store = InMemoryChatSettingsStore()
        handle_add_task(
            chat_id=_CHAT,
            args=["DISHWASHER"],
            client=_mock_client(),
            settings_store=store,
            lang=Language.EN,
        )
        assert store.get(_CHAT).enabled_tasks == ["laundry", "dishwasher"]  # type: ignore[union-attr]

    def test_already_enabled_is_a_no_op(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(ChatSettings(chat_id=_CHAT, enabled_tasks=["laundry"], updated_at=utcnow()))
        client = _mock_client()
        handle_add_task(
            chat_id=_CHAT, args=["laundry"], client=client, settings_store=store, lang=Language.EN
        )
        assert store.get(_CHAT).enabled_tasks == ["laundry"]  # type: ignore[union-attr]
        _, kwargs = client.send_message.call_args
        assert "already" in kwargs["text"].lower()

    def test_preserves_language_and_profile(self) -> None:
        from hrse.models.chat_settings import TaskProfile

        store = InMemoryChatSettingsStore()
        store.save(
            ChatSettings(
                chat_id=_CHAT,
                language=Language.ZH,
                profiles={"laundry": TaskProfile(target_per_week=3)},
                enabled_tasks=["laundry"],
                updated_at=utcnow(),
            )
        )
        handle_add_task(
            chat_id=_CHAT,
            args=["ev"],
            client=_mock_client(),
            settings_store=store,
            lang=Language.EN,
        )
        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.language is Language.ZH
        assert saved.profiles.get("laundry") is not None
        assert saved.profiles["laundry"].target_per_week == 3
        assert saved.enabled_tasks == ["laundry", "ev"]

    def test_preserves_onboarding_complete(self) -> None:
        # Regression guard: /add_task must not silently unregister an
        # already-onboarded chat from daily notifications.
        store = InMemoryChatSettingsStore()
        store.save(
            ChatSettings(
                chat_id=_CHAT,
                onboarding_complete=True,
                enabled_tasks=["laundry"],
                updated_at=utcnow(),
            )
        )
        handle_add_task(
            chat_id=_CHAT,
            args=["ev"],
            client=_mock_client(),
            settings_store=store,
            lang=Language.EN,
        )
        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.onboarding_complete is True

    def test_confirmation_sent_to_correct_chat(self) -> None:
        client = _mock_client()
        handle_add_task(
            chat_id=99,
            args=["ev"],
            client=client,
            settings_store=InMemoryChatSettingsStore(),
            lang=Language.EN,
        )
        _, kwargs = client.send_message.call_args
        assert kwargs["chat_id"] == 99


# ---------------------------------------------------------------------------
# handle_remove_task
# ---------------------------------------------------------------------------


class TestHandleRemoveTask:
    def test_no_args_sends_usage(self) -> None:
        client = _mock_client()
        handle_remove_task(
            chat_id=_CHAT,
            args=[],
            client=client,
            settings_store=InMemoryChatSettingsStore(),
            lang=Language.EN,
        )
        _, kwargs = client.send_message.call_args
        assert "Usage" in kwargs["text"]

    def test_removes_enabled_task(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(
            ChatSettings(
                chat_id=_CHAT, enabled_tasks=["laundry", "dishwasher"], updated_at=utcnow()
            )
        )
        handle_remove_task(
            chat_id=_CHAT,
            args=["dishwasher"],
            client=_mock_client(),
            settings_store=store,
            lang=Language.EN,
        )
        assert store.get(_CHAT).enabled_tasks == ["laundry"]  # type: ignore[union-attr]

    def test_removing_not_enabled_task_is_a_no_op(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(ChatSettings(chat_id=_CHAT, enabled_tasks=["laundry"], updated_at=utcnow()))
        client = _mock_client()
        handle_remove_task(
            chat_id=_CHAT, args=["ev"], client=client, settings_store=store, lang=Language.EN
        )
        assert store.get(_CHAT).enabled_tasks == ["laundry"]  # type: ignore[union-attr]
        _, kwargs = client.send_message.call_args
        assert "isn't enabled" in kwargs["text"] or "未啟用" in kwargs["text"]

    def test_can_remove_down_to_empty_list(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(ChatSettings(chat_id=_CHAT, enabled_tasks=["laundry"], updated_at=utcnow()))
        handle_remove_task(
            chat_id=_CHAT,
            args=["laundry"],
            client=_mock_client(),
            settings_store=store,
            lang=Language.EN,
        )
        assert store.get(_CHAT).enabled_tasks == []  # type: ignore[union-attr]

    def test_no_stored_settings_defaults_enabled_to_laundry_before_removal(self) -> None:
        store = InMemoryChatSettingsStore()
        handle_remove_task(
            chat_id=_CHAT,
            args=["laundry"],
            client=_mock_client(),
            settings_store=store,
            lang=Language.EN,
        )
        assert store.get(_CHAT).enabled_tasks == []  # type: ignore[union-attr]
