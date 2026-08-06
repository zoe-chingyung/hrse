"""Unit tests for the Sprint 5B /setup onboarding conversation, /profile, /reset.

Sprint B: step 0 of /setup is now the postcode/region question — every
happy-path test below completes it first via ``_complete_postcode_step``
before answering the original 6 TaskProfile questions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from hrse.models.chat_settings import ChatSettings, Language, TaskProfile
from hrse.store.chat_settings_store import InMemoryChatSettingsStore
from hrse.telegram.commands import (
    handle_onboarding_answer,
    handle_profile,
    handle_reset,
    handle_setup_start,
)
from hrse.utils.datetime_utils import utcnow

if TYPE_CHECKING:
    from datetime import datetime

    from hrse.models.pricing import PricePoint

_CHAT = -100123


class _StubOctopus:
    """Returns a fixed GSP region letter for lookup_gsp; get_prices unused here."""

    def __init__(self, region: str | None = "C") -> None:
        self._region = region
        self.lookup_calls: list[str] = []

    def get_prices(self, period_from: datetime, period_to: datetime) -> list[PricePoint]:
        return []

    def lookup_gsp(self, postcode: str) -> str | None:
        self.lookup_calls.append(postcode)
        return self._region


def _mock_client() -> MagicMock:
    return MagicMock()


def _answer(
    store: InMemoryChatSettingsStore,
    client: MagicMock,
    text: str,
    lang: Language = Language.EN,
    octopus: _StubOctopus | None = None,
) -> None:
    handle_onboarding_answer(
        chat_id=_CHAT,
        text=text,
        client=client,
        settings_store=store,
        lang=lang,
        octopus=octopus if octopus is not None else _StubOctopus(),
    )


def _complete_postcode_step(
    store: InMemoryChatSettingsStore, client: MagicMock, region: str = "C"
) -> None:
    """Answer the postcode/region question so a fresh /setup reaches step 1."""
    _answer(store, client, "SW1A 1AA", octopus=_StubOctopus(region))


# ---------------------------------------------------------------------------
# handle_setup_start
# ---------------------------------------------------------------------------


class TestHandleSetupStart:
    def test_saves_fresh_profile_at_step_zero(self) -> None:
        store = InMemoryChatSettingsStore()
        handle_setup_start(
            chat_id=_CHAT, client=_mock_client(), settings_store=store, lang=Language.EN
        )

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.onboarding_step == 0
        assert saved.profiles["laundry"] == TaskProfile()

    def test_sends_postcode_question_first(self) -> None:
        client = _mock_client()
        handle_setup_start(
            chat_id=_CHAT,
            client=client,
            settings_store=InMemoryChatSettingsStore(),
            lang=Language.EN,
        )

        _, kwargs = client.send_message.call_args
        assert kwargs["chat_id"] == _CHAT
        assert "1/7" in kwargs["text"]
        assert "postcode" in kwargs["text"].lower()

    def test_sends_target_question_after_postcode_resolved(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()
        handle_setup_start(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)

        _complete_postcode_step(store, client)

        _, kwargs = client.send_message.call_args
        assert "2/7" in kwargs["text"]
        assert "laundry runs" in kwargs["text"].lower()

    def test_restart_resets_to_step_zero_with_fresh_defaults(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(
            ChatSettings(
                chat_id=_CHAT,
                profiles={"laundry": TaskProfile(target_per_week=9)},
                onboarding_step=4,
                updated_at=utcnow(),
            )
        )
        handle_setup_start(
            chat_id=_CHAT, client=_mock_client(), settings_store=store, lang=Language.EN
        )

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.onboarding_step == 0
        assert saved.profiles["laundry"] == TaskProfile()

    def test_preserves_passed_language(self) -> None:
        store = InMemoryChatSettingsStore()
        handle_setup_start(
            chat_id=_CHAT, client=_mock_client(), settings_store=store, lang=Language.ZH
        )
        assert store.get(_CHAT).language is Language.ZH  # type: ignore[union-attr]

    def test_preserves_enabled_tasks(self) -> None:
        # Regression guard: /setup must not silently reset enabled_tasks
        # back to the ["laundry"] default for a chat that has customised it.
        store = InMemoryChatSettingsStore()
        store.save(
            ChatSettings(
                chat_id=_CHAT, enabled_tasks=["laundry", "dishwasher"], updated_at=utcnow()
            )
        )
        handle_setup_start(
            chat_id=_CHAT, client=_mock_client(), settings_store=store, lang=Language.EN
        )
        assert store.get(_CHAT).enabled_tasks == ["laundry", "dishwasher"]  # type: ignore[union-attr]

    def test_preserves_other_task_profiles(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(
            ChatSettings(
                chat_id=_CHAT,
                profiles={"dishwasher": TaskProfile(target_per_week=7)},
                updated_at=utcnow(),
            )
        )
        handle_setup_start(
            chat_id=_CHAT, client=_mock_client(), settings_store=store, lang=Language.EN
        )
        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.profiles["dishwasher"] == TaskProfile(target_per_week=7)
        assert saved.profiles["laundry"] == TaskProfile()

    def test_preserves_onboarding_complete_when_restarting(self) -> None:
        # Regression guard: re-running /setup on an already-registered chat
        # must not silently drop it from daily-notification recipients.
        store = InMemoryChatSettingsStore()
        store.save(ChatSettings(chat_id=_CHAT, onboarding_complete=True, updated_at=utcnow()))
        handle_setup_start(
            chat_id=_CHAT, client=_mock_client(), settings_store=store, lang=Language.EN
        )
        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.onboarding_complete is True

    def test_preserves_octopus_region_code_when_restarting(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(ChatSettings(chat_id=_CHAT, octopus_region_code="H", updated_at=utcnow()))
        handle_setup_start(
            chat_id=_CHAT, client=_mock_client(), settings_store=store, lang=Language.EN
        )
        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.octopus_region_code == "H"


# ---------------------------------------------------------------------------
# handle_onboarding_answer — step 0 (postcode / region)
# ---------------------------------------------------------------------------


class TestPostcodeStep:
    def test_valid_postcode_resolves_region_and_advances(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()
        handle_setup_start(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)

        _answer(store, client, "SW1A 1AA", octopus=_StubOctopus("C"))

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.octopus_region_code == "C"
        assert saved.onboarding_step == 1
        _, kwargs = client.send_message.call_args
        assert "2/7" in kwargs["text"]

    def test_region_confirmation_message_shows_letter(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()
        handle_setup_start(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)

        _answer(store, client, "SW1A 1AA", octopus=_StubOctopus("C"))

        confirmation_texts = [call.kwargs["text"] for call in client.send_message.call_args_list]
        assert any("C" in text for text in confirmation_texts)

    def test_failed_lookup_shows_manual_picker_and_does_not_advance(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()
        handle_setup_start(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)

        _answer(store, client, "not a real postcode", octopus=_StubOctopus(None))

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.octopus_region_code is None
        assert saved.onboarding_step == 0
        _, kwargs = client.send_message.call_args
        assert kwargs["reply_markup"]["inline_keyboard"]

    def test_no_octopus_client_shows_manual_picker(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()
        handle_setup_start(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)

        handle_onboarding_answer(
            chat_id=_CHAT,
            text="SW1A 1AA",
            client=client,
            settings_store=store,
            lang=Language.EN,
            octopus=None,
        )

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.octopus_region_code is None
        assert saved.onboarding_step == 0
        _, kwargs = client.send_message.call_args
        assert kwargs["reply_markup"]["inline_keyboard"]

    def test_can_retry_postcode_after_failed_lookup(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()
        handle_setup_start(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)

        _answer(store, client, "bad postcode", octopus=_StubOctopus(None))
        assert store.get(_CHAT).onboarding_step == 0  # type: ignore[union-attr]

        _answer(store, client, "SW1A 1AA", octopus=_StubOctopus("C"))
        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.octopus_region_code == "C"
        assert saved.onboarding_step == 1


# ---------------------------------------------------------------------------
# handle_onboarding_answer — full happy path
# ---------------------------------------------------------------------------


class TestOnboardingHappyPath:
    def test_six_valid_answers_produce_correct_profile(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()
        handle_setup_start(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)
        _complete_postcode_step(store, client)

        _answer(store, client, "3")
        _answer(store, client, "07:00")
        _answer(store, client, "21:00")
        _answer(store, client, "yes")
        _answer(store, client, "Europe/London")
        _answer(store, client, "35")

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.onboarding_step is None
        assert saved.octopus_region_code == "C"
        profile = saved.profiles.get("laundry")
        assert profile is not None
        assert profile.target_per_week == 3
        assert profile.earliest_start == "07:00"
        assert profile.latest_finish == "21:00"
        assert profile.outdoor_drying is True
        assert profile.timezone == "Europe/London"
        assert profile.wash_budget_pence == 35.0
        # Not asked — keeps TaskProfile defaults.
        assert profile.duration_slots == 4
        assert profile.machine_kwh == 1.5
        assert profile.min_uv == 3.0
        assert profile.max_rain_probability == 40
        assert saved.onboarding_complete is True

    def test_final_step_sends_setup_done(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()
        handle_setup_start(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)
        _complete_postcode_step(store, client)
        for answer in ("2", "08:00", "22:00", "no", "Europe/London", "40"):
            _answer(store, client, answer)

        _, kwargs = client.send_message.call_args
        assert "complete" in kwargs["text"].lower()

    def test_intermediate_steps_advance_and_ask_next_question(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()
        handle_setup_start(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)
        _complete_postcode_step(store, client)

        _answer(store, client, "2")
        assert store.get(_CHAT).onboarding_step == 2  # type: ignore[union-attr]
        _, kwargs = client.send_message.call_args
        assert "3/7" in kwargs["text"]
        assert "earliest" in kwargs["text"].lower()

    def test_intermediate_step_does_not_set_onboarding_complete(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()
        handle_setup_start(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)
        _complete_postcode_step(store, client)

        _answer(store, client, "2")
        assert store.get(_CHAT).onboarding_complete is False  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# handle_onboarding_answer — validation failures re-ask the same step
# ---------------------------------------------------------------------------


class TestOnboardingValidation:
    def test_non_numeric_target_reasks_same_step(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()
        handle_setup_start(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)
        _complete_postcode_step(store, client)

        _answer(store, client, "not-a-number")

        assert store.get(_CHAT).onboarding_step == 1  # type: ignore[union-attr]
        _, kwargs = client.send_message.call_args
        assert "2/7" in kwargs["text"]
        assert "⚠️" in kwargs["text"]

    def test_zero_target_reasks_same_step(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()
        handle_setup_start(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)
        _complete_postcode_step(store, client)

        _answer(store, client, "0")
        assert store.get(_CHAT).onboarding_step == 1  # type: ignore[union-attr]

    def test_invalid_hhmm_reasks_same_step(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()
        handle_setup_start(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)
        _complete_postcode_step(store, client)
        _answer(store, client, "2")  # advance to earliest_start

        _answer(store, client, "not-a-time")
        assert store.get(_CHAT).onboarding_step == 2  # type: ignore[union-attr]

    def test_latest_before_earliest_reasks_same_step(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()
        handle_setup_start(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)
        _complete_postcode_step(store, client)
        _answer(store, client, "2")  # -> earliest_start
        _answer(store, client, "20:00")  # -> latest_finish

        _answer(store, client, "08:00")  # before earliest_start (20:00)
        assert store.get(_CHAT).onboarding_step == 3  # type: ignore[union-attr]
        assert store.get(_CHAT).profiles["laundry"].latest_finish == "22:00"  # type: ignore[union-attr]

    def test_unrecognised_yes_no_reasks_same_step(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()
        handle_setup_start(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)
        _complete_postcode_step(store, client)
        _answer(store, client, "2")
        _answer(store, client, "08:00")
        _answer(store, client, "22:00")

        _answer(store, client, "maybe")
        assert store.get(_CHAT).onboarding_step == 4  # type: ignore[union-attr]

    def test_unknown_timezone_reasks_same_step(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()
        handle_setup_start(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)
        _complete_postcode_step(store, client)
        for answer in ("2", "08:00", "22:00", "yes"):
            _answer(store, client, answer)

        _answer(store, client, "Mars/Colony_One")
        assert store.get(_CHAT).onboarding_step == 5  # type: ignore[union-attr]

    def test_non_numeric_budget_reasks_same_step(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()
        handle_setup_start(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)
        _complete_postcode_step(store, client)
        for answer in ("2", "08:00", "22:00", "yes", "Europe/London"):
            _answer(store, client, answer)

        _answer(store, client, "free")
        assert store.get(_CHAT).onboarding_step == 6  # type: ignore[union-attr]

    def test_zero_budget_reasks_same_step(self) -> None:
        store = InMemoryChatSettingsStore()
        client = _mock_client()
        handle_setup_start(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)
        _complete_postcode_step(store, client)
        for answer in ("2", "08:00", "22:00", "yes", "Europe/London"):
            _answer(store, client, answer)

        _answer(store, client, "0")
        assert store.get(_CHAT).onboarding_step == 6  # type: ignore[union-attr]


class TestOnboardingDefensive:
    def test_answer_without_active_onboarding_falls_back_to_unknown(self) -> None:
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
    def test_no_profile_sends_profile_none(self) -> None:
        client = _mock_client()
        handle_profile(
            chat_id=_CHAT,
            client=client,
            settings_store=InMemoryChatSettingsStore(),
            lang=Language.EN,
        )
        _, kwargs = client.send_message.call_args
        assert "no personal settings" in kwargs["text"].lower()

    def test_with_profile_shows_fields(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(
            ChatSettings(
                chat_id=_CHAT,
                profiles={
                    "laundry": TaskProfile(
                        target_per_week=3,
                        earliest_start="07:00",
                        latest_finish="21:00",
                        wash_budget_pence=35.0,
                        outdoor_drying=False,
                        timezone="Europe/London",
                    )
                },
                updated_at=utcnow(),
            )
        )
        client = _mock_client()
        handle_profile(chat_id=_CHAT, client=client, settings_store=store, lang=Language.EN)

        _, kwargs = client.send_message.call_args
        text = kwargs["text"]
        assert "3" in text
        assert "07:00" in text
        assert "21:00" in text
        assert "35" in text
        assert "❌" in text  # outdoor_drying False
        assert "Europe/London" in text

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
    def test_clears_profile_and_onboarding_step(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(
            ChatSettings(
                chat_id=_CHAT,
                language=Language.ZH,
                profiles={"laundry": TaskProfile(target_per_week=5)},
                onboarding_step=2,
                updated_at=utcnow(),
            )
        )
        handle_reset(chat_id=_CHAT, client=_mock_client(), settings_store=store, lang=Language.EN)

        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.profiles == {}
        assert saved.onboarding_step is None
        assert saved.language is Language.ZH  # preserved, not overwritten by the passed-in lang

    def test_reset_clears_onboarding_complete(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(ChatSettings(chat_id=_CHAT, onboarding_complete=True, updated_at=utcnow()))
        handle_reset(chat_id=_CHAT, client=_mock_client(), settings_store=store, lang=Language.EN)
        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.onboarding_complete is False

    def test_reset_preserves_enabled_tasks(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(
            ChatSettings(
                chat_id=_CHAT, enabled_tasks=["laundry", "dishwasher"], updated_at=utcnow()
            )
        )
        handle_reset(chat_id=_CHAT, client=_mock_client(), settings_store=store, lang=Language.EN)
        assert store.get(_CHAT).enabled_tasks == ["laundry", "dishwasher"]  # type: ignore[union-attr]

    def test_reset_preserves_octopus_region_code(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(ChatSettings(chat_id=_CHAT, octopus_region_code="H", updated_at=utcnow()))
        handle_reset(chat_id=_CHAT, client=_mock_client(), settings_store=store, lang=Language.EN)
        saved = store.get(_CHAT)
        assert saved is not None
        assert saved.octopus_region_code == "H"

    def test_sends_confirmation(self) -> None:
        client = _mock_client()
        handle_reset(
            chat_id=_CHAT,
            client=client,
            settings_store=InMemoryChatSettingsStore(),
            lang=Language.EN,
        )
        client.send_message.assert_called_once()

    def test_reset_with_no_prior_settings_uses_passed_language(self) -> None:
        store = InMemoryChatSettingsStore()
        handle_reset(chat_id=_CHAT, client=_mock_client(), settings_store=store, lang=Language.ZH)
        assert store.get(_CHAT).language is Language.ZH  # type: ignore[union-attr]
