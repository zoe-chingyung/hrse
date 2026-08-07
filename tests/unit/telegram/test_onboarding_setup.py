"""Unit tests for the Sprint C button-driven onboarding: task multi-select,
per-task button config, /profile, /reset.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from hrse.models.chat_settings import ChatSettings, Language, TaskProfile
from hrse.models.telegram import TelegramCallbackQuery, TelegramChat, TelegramMessage
from hrse.store.chat_settings_store import InMemoryChatSettingsStore
from hrse.telegram.commands import (
    TASK_DONE_CALLBACK_DATA,
    handle_config_callback,
    handle_onboarding_answer,
    handle_profile,
    handle_reset,
    handle_task_done_callback,
    handle_task_toggle_callback,
)
from hrse.utils.datetime_utils import utcnow

_CHAT = -100123


def _mock_client() -> MagicMock:
    return MagicMock()


def _callback(data: str | None, with_message: bool = True) -> TelegramCallbackQuery:
    message = TelegramMessage(message_id=55, chat=TelegramChat(id=_CHAT)) if with_message else None
    return TelegramCallbackQuery.model_validate(
        {
            "id": "cb-1",
            "from": {"id": 42, "is_bot": False, "first_name": "Zoe"},
            "message": message.model_dump() if message else None,
            "data": data,
        }
    )


def _tasks_stage_settings(**overrides: object) -> ChatSettings:
    base: dict[str, object] = {
        "chat_id": _CHAT,
        "onboarding_stage": "tasks",
        "updated_at": utcnow(),
    }
    base.update(overrides)
    return ChatSettings(**base)  # type: ignore[arg-type]


def _config_stage_settings(**overrides: object) -> ChatSettings:
    base: dict[str, object] = {
        "chat_id": _CHAT,
        "onboarding_stage": "config",
        "pending_config_queue": ["laundry"],
        "onboarding_task_step": 0,
        "profiles": {"laundry": TaskProfile()},
        "enabled_tasks": ["laundry"],
        "updated_at": utcnow(),
    }
    base.update(overrides)
    return ChatSettings(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Multi-select task picker
# ---------------------------------------------------------------------------


class TestHandleTaskToggleCallback:
    def test_toggling_adds_task_to_selection(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_tasks_stage_settings())
        client = _mock_client()

        handle_task_toggle_callback(
            query=_callback("task:laundry"), client=client, settings_store=store
        )

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.pending_task_selection == ["laundry"]

    def test_toggling_again_removes_task(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_tasks_stage_settings(pending_task_selection=["laundry"]))
        client = _mock_client()

        handle_task_toggle_callback(
            query=_callback("task:laundry"), client=client, settings_store=store
        )

        assert store.get(_CHAT).pending_task_selection == []  # type: ignore[union-attr]

    def test_redraws_keyboard_with_updated_checkmarks(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_tasks_stage_settings())
        client = _mock_client()

        handle_task_toggle_callback(query=_callback("task:ev"), client=client, settings_store=store)

        _, kwargs = client.edit_message_text.call_args
        buttons = [b for row in kwargs["reply_markup"]["inline_keyboard"] for b in row]
        ev_button = next(b for b in buttons if b["callback_data"] == "task:ev")
        assert "✅" in ev_button["text"]

    def test_unknown_task_key_is_ignored(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_tasks_stage_settings())
        client = _mock_client()

        handle_task_toggle_callback(
            query=_callback("task:gardening"), client=client, settings_store=store
        )

        assert store.get(_CHAT).pending_task_selection == []  # type: ignore[union-attr]
        client.answer_callback_query.assert_called_once()

    def test_stale_press_outside_tasks_stage_is_ignored(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_config_stage_settings())
        client = _mock_client()

        handle_task_toggle_callback(
            query=_callback("task:laundry"), client=client, settings_store=store
        )

        assert store.get(_CHAT).pending_task_selection == []  # type: ignore[union-attr]
        client.edit_message_text.assert_not_called()


class TestHandleTaskDoneCallback:
    def test_zero_selection_blocks_and_reshows_picker(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_tasks_stage_settings())
        client = _mock_client()

        handle_task_done_callback(
            query=_callback(TASK_DONE_CALLBACK_DATA), client=client, settings_store=store
        )

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.onboarding_stage == "tasks"
        _, kwargs = client.edit_message_text.call_args
        assert kwargs["reply_markup"]["inline_keyboard"]

    def test_locks_in_selection_and_creates_default_profiles(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_tasks_stage_settings(pending_task_selection=["ev", "laundry"]))
        client = _mock_client()

        handle_task_done_callback(
            query=_callback(TASK_DONE_CALLBACK_DATA), client=client, settings_store=store
        )

        saved = store.get(_CHAT)
        assert saved is not None
        # Canonical TASK_ORDER, not selection order.
        assert saved.enabled_tasks == ["laundry", "ev"]
        assert set(saved.profiles) == {"laundry", "ev"}
        assert saved.onboarding_stage == "config"
        assert saved.pending_config_queue == ["laundry", "ev"]

    def test_dishwasher_default_profile_has_weather_off(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_tasks_stage_settings(pending_task_selection=["dishwasher"]))
        client = _mock_client()

        handle_task_done_callback(
            query=_callback(TASK_DONE_CALLBACK_DATA), client=client, settings_store=store
        )

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.profiles["dishwasher"].weather_aware is False

    def test_laundry_default_profile_has_weather_on(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_tasks_stage_settings(pending_task_selection=["laundry"]))
        client = _mock_client()

        handle_task_done_callback(
            query=_callback(TASK_DONE_CALLBACK_DATA), client=client, settings_store=store
        )

        assert store.get(_CHAT).profiles["laundry"].weather_aware is True  # type: ignore[union-attr]

    def test_sends_first_config_question(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_tasks_stage_settings(pending_task_selection=["laundry"]))
        client = _mock_client()

        handle_task_done_callback(
            query=_callback(TASK_DONE_CALLBACK_DATA), client=client, settings_store=store
        )

        _, kwargs = client.send_message.call_args
        assert "1/9" in kwargs["text"]
        assert kwargs["reply_markup"]["inline_keyboard"]

    def test_stale_press_outside_tasks_stage_is_ignored(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_config_stage_settings())
        client = _mock_client()

        handle_task_done_callback(
            query=_callback(TASK_DONE_CALLBACK_DATA), client=client, settings_store=store
        )

        client.edit_message_text.assert_not_called()
        client.send_message.assert_not_called()


# ---------------------------------------------------------------------------
# Per-task button config
# ---------------------------------------------------------------------------


class TestHandleConfigCallback:
    def test_button_answer_saves_field_and_advances(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_config_stage_settings())
        client = _mock_client()

        handle_config_callback(
            query=_callback("cfg:target_per_week:3"), client=client, settings_store=store
        )

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.profiles["laundry"].target_per_week == 3
        assert saved.onboarding_task_step == 1

    def test_final_question_of_only_task_completes_onboarding(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(
            _config_stage_settings(
                pending_config_queue=["ev"],
                profiles={"ev": TaskProfile(weather_aware=False)},
                enabled_tasks=["ev"],
            )
        )
        client = _mock_client()

        handle_config_callback(
            query=_callback("cfg:duration_slots:16"), client=client, settings_store=store
        )

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.onboarding_complete is True
        assert saved.onboarding_stage is None
        assert saved.profiles["ev"].duration_slots == 16
        _, kwargs = client.send_message.call_args
        assert "complete" in kwargs["text"].lower()

    def test_last_question_of_task_advances_to_next_task_in_queue(self) -> None:
        # ev has exactly one question, so answering it should move straight
        # to the next task in the queue instead of finishing onboarding.
        store = InMemoryChatSettingsStore()
        store.save(
            _config_stage_settings(
                pending_config_queue=["ev", "laundry"],
                profiles={"ev": TaskProfile(weather_aware=False), "laundry": TaskProfile()},
                enabled_tasks=["ev", "laundry"],
            )
        )
        client = _mock_client()

        handle_config_callback(
            query=_callback("cfg:duration_slots:16"), client=client, settings_store=store
        )

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.pending_config_queue == ["laundry"]
        assert saved.onboarding_task_step == 0
        assert saved.onboarding_complete is False

    def test_other_button_sets_awaiting_typed_field(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_config_stage_settings())
        client = _mock_client()

        handle_config_callback(
            query=_callback("cfg:target_per_week:other"), client=client, settings_store=store
        )

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.awaiting_typed_field == "target_per_week"
        assert saved.onboarding_task_step == 0  # not yet advanced

    def test_stale_field_from_previous_question_is_ignored(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_config_stage_settings(onboarding_task_step=1))  # now on duration_slots
        client = _mock_client()

        handle_config_callback(
            query=_callback("cfg:target_per_week:3"), client=client, settings_store=store
        )

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.profiles["laundry"].target_per_week == 2  # unchanged (default)

    def test_invalid_value_reshows_question_with_error(self) -> None:
        store = InMemoryChatSettingsStore()
        # earliest_start set later than every latest_finish button option (20:00-23:00),
        # so any button press here trips the finish-after-start validator.
        store.save(
            _config_stage_settings(
                onboarding_task_step=4,  # latest_finish
                profiles={"laundry": TaskProfile(earliest_start="23:30", latest_finish="23:59")},
            )
        )
        client = _mock_client()

        handle_config_callback(
            query=_callback("cfg:latest_finish:20:00"), client=client, settings_store=store
        )

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.onboarding_task_step == 4  # unchanged
        _, kwargs = client.edit_message_text.call_args
        assert "⚠️" in kwargs["text"]

    def test_dishwasher_question_table_never_asks_about_weather(self) -> None:
        from hrse.telegram.commands import _TASK_QUESTIONS

        dishwasher_fields = {q.field for q in _TASK_QUESTIONS["dishwasher"]}
        assert dishwasher_fields.isdisjoint({"min_uv", "max_rain_probability", "outdoor_drying"})

    def test_dishwasher_last_question_completes_onboarding(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(
            _config_stage_settings(
                pending_config_queue=["dishwasher"],
                profiles={"dishwasher": TaskProfile(weather_aware=False)},
                enabled_tasks=["dishwasher"],
                onboarding_task_step=5,  # dishwasher's last question (0-indexed, 6 total)
            )
        )
        client = _mock_client()

        handle_config_callback(
            query=_callback("cfg:timezone:Europe/London"), client=client, settings_store=store
        )

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.onboarding_complete is True
        assert saved.profiles["dishwasher"].weather_aware is False


class TestHandleOnboardingAnswerConfigStage:
    def test_typed_other_answer_saves_field_and_advances(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_config_stage_settings(awaiting_typed_field="target_per_week"))
        client = _mock_client()

        handle_onboarding_answer(
            chat_id=_CHAT, text="9", client=client, settings_store=store, lang=Language.EN
        )

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.profiles["laundry"].target_per_week == 9
        assert saved.awaiting_typed_field is None
        assert saved.onboarding_task_step == 1

    def test_invalid_typed_answer_reasks(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_config_stage_settings(awaiting_typed_field="target_per_week"))
        client = _mock_client()

        handle_onboarding_answer(
            chat_id=_CHAT,
            text="not-a-number",
            client=client,
            settings_store=store,
            lang=Language.EN,
        )

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.awaiting_typed_field == "target_per_week"
        _, kwargs = client.send_message.call_args
        assert "⚠️" in kwargs["text"]

    def test_plain_text_without_awaiting_field_gets_button_hint(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_config_stage_settings())
        client = _mock_client()

        handle_onboarding_answer(
            chat_id=_CHAT, text="hello", client=client, settings_store=store, lang=Language.EN
        )

        _, kwargs = client.send_message.call_args
        assert "button" in kwargs["text"].lower()

    def test_plain_text_during_tasks_stage_gets_button_hint(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_tasks_stage_settings())
        client = _mock_client()

        handle_onboarding_answer(
            chat_id=_CHAT, text="laundry", client=client, settings_store=store, lang=Language.EN
        )

        _, kwargs = client.send_message.call_args
        assert "button" in kwargs["text"].lower()

    def test_no_active_onboarding_falls_back_to_unknown(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()

        handle_onboarding_answer(
            chat_id=_CHAT, text="hello", client=client, settings_store=store, lang=Language.EN
        )

        _, kwargs = client.send_message.call_args
        assert "unknown" in kwargs["text"].lower() or "🤖" in kwargs["text"]


# ---------------------------------------------------------------------------
# handle_profile
# ---------------------------------------------------------------------------


class TestHandleProfile:
    def test_no_profiles_sends_profile_none(self) -> None:
        client = _mock_client()
        handle_profile(
            chat_id=_CHAT,
            client=client,
            settings_store=InMemoryChatSettingsStore(),
            lang=Language.EN,
        )
        _, kwargs = client.send_message.call_args
        assert "no tasks configured" in kwargs["text"].lower()

    def test_shows_a_block_per_configured_task(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(
            ChatSettings(
                chat_id=_CHAT,
                profiles={
                    "laundry": TaskProfile(target_per_week=3, wash_budget_pence=35.0),
                    "dishwasher": TaskProfile(target_per_week=5, weather_aware=False),
                },
                updated_at=utcnow(),
            )
        )
        client = _mock_client()
        handle_profile(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)

        _, kwargs = client.send_message.call_args
        text = kwargs["text"]
        assert "Laundry" in text
        assert "Dishwasher" in text
        assert "35" in text

    def test_zh_variant_differs(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(
            ChatSettings(chat_id=_CHAT, profiles={"laundry": TaskProfile()}, updated_at=utcnow())
        )
        client = _mock_client()
        handle_profile(chat_id=_CHAT, client=client, settings_store=store, lang=Language.ZH)
        _, kwargs = client.send_message.call_args
        assert "你嘅設定" in kwargs["text"]


# ---------------------------------------------------------------------------
# handle_reset
# ---------------------------------------------------------------------------


class TestHandleReset:
    def test_clears_profiles_and_onboarding_state(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(
            ChatSettings(
                chat_id=_CHAT,
                language=Language.ZH,
                profiles={"laundry": TaskProfile(target_per_week=5)},
                enabled_tasks=["laundry"],
                onboarding_stage="config",
                pending_config_queue=["laundry"],
                updated_at=utcnow(),
            )
        )
        handle_reset(chat_id=_CHAT, client=_mock_client(), settings_store=store, lang=Language.EN)

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.profiles == {}
        assert saved.enabled_tasks == []
        assert saved.onboarding_stage is None
        assert saved.pending_config_queue == []
        assert saved.language is Language.ZH  # preserved, not overwritten by the passed-in lang

    def test_reset_clears_onboarding_complete(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(ChatSettings(chat_id=_CHAT, onboarding_complete=True, updated_at=utcnow()))
        handle_reset(chat_id=_CHAT, client=_mock_client(), settings_store=store, lang=Language.EN)
        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.onboarding_complete is False

    def test_reset_preserves_octopus_region_code(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(ChatSettings(chat_id=_CHAT, octopus_region_code="H", updated_at=utcnow()))
        handle_reset(chat_id=_CHAT, client=_mock_client(), settings_store=store, lang=Language.EN)
        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.octopus_region_code == "H"

    def test_sends_confirmation_then_restarts_welcome_flow(self) -> None:
        client = _mock_client()
        handle_reset(
            chat_id=_CHAT,
            client=client,
            settings_store=InMemoryChatSettingsStore(),
            lang=Language.EN,
        )
        assert client.send_message.call_count == 2
        first_text = client.send_message.call_args_list[0].kwargs["text"]
        second_kwargs = client.send_message.call_args_list[1].kwargs
        assert "cleared" in first_text.lower()
        assert "Hello" in second_kwargs["text"]
        assert second_kwargs["reply_markup"]["inline_keyboard"]

    def test_reset_with_no_prior_settings_uses_passed_language(self) -> None:
        store = InMemoryChatSettingsStore()
        handle_reset(chat_id=_CHAT, client=_mock_client(), settings_store=store, lang=Language.ZH)
        assert store.get(_CHAT).language is Language.ZH  # type: ignore[union-attr]

    def test_reset_is_idempotent_mid_onboarding(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(
            ChatSettings(
                chat_id=_CHAT,
                onboarding_stage="tasks",
                pending_task_selection=["laundry"],
                updated_at=utcnow(),
            )
        )
        client = _mock_client()
        handle_reset(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)
        handle_reset(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.onboarding_stage is None
        assert saved.pending_task_selection == []
