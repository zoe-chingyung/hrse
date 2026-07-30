"""Unit tests for chat settings models and the i18n message catalogue.

Sprint 6 — Group onboarding & language.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from hrse.i18n import MessageKey, bilingual_welcome, t
from hrse.i18n.messages import _CATALOGUE  # noqa: PLC2701 — completeness check
from hrse.models.chat_settings import ChatSettings, Language, TaskProfile

_NOW = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Language / ChatSettings models
# ---------------------------------------------------------------------------


class TestLanguage:
    def test_values_match_callback_suffixes(self) -> None:
        assert Language.EN == "en"
        assert Language.ZH == "zh"

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValueError, match="fr"):
            Language("fr")


class TestChatSettings:
    def test_defaults_to_english(self) -> None:
        settings = ChatSettings(chat_id=1, updated_at=_NOW)
        assert settings.language is Language.EN

    def test_accepts_negative_group_chat_id(self) -> None:
        settings = ChatSettings(chat_id=-100123, language=Language.ZH, updated_at=_NOW)
        assert settings.chat_id == -100123

    def test_is_frozen(self) -> None:
        settings = ChatSettings(chat_id=1, updated_at=_NOW)
        with pytest.raises(ValidationError):
            settings.language = Language.ZH  # type: ignore[misc]

    def test_json_round_trip(self) -> None:
        original = ChatSettings(chat_id=-5, language=Language.ZH, updated_at=_NOW)
        restored = ChatSettings.model_validate_json(original.model_dump_json())
        assert restored == original

    def test_defaults_profiles_and_onboarding_step_to_empty(self) -> None:
        settings = ChatSettings(chat_id=1, updated_at=_NOW)
        assert settings.profiles == {}
        assert settings.onboarding_step is None

    def test_json_round_trip_with_full_profile(self) -> None:
        original = ChatSettings(
            chat_id=-5,
            language=Language.ZH,
            profiles={"laundry": TaskProfile(target_per_week=3, timezone="Asia/Hong_Kong")},
            onboarding_step=2,
            updated_at=_NOW,
        )
        restored = ChatSettings.model_validate_json(original.model_dump_json())
        assert restored == original

    def test_json_round_trip_with_multiple_task_profiles(self) -> None:
        original = ChatSettings(
            chat_id=-5,
            profiles={
                "laundry": TaskProfile(target_per_week=3),
                "dishwasher": TaskProfile(target_per_week=7, wash_budget_pence=20.0),
            },
            updated_at=_NOW,
        )
        restored = ChatSettings.model_validate_json(original.model_dump_json())
        assert restored == original

    def test_old_json_without_profiles_field_still_loads(self) -> None:
        # Pre-5B persisted JSON never had `profile`/`profiles`/`onboarding_step` keys.
        old_json = ChatSettings(chat_id=1, language=Language.EN, updated_at=_NOW).model_dump_json(
            exclude={"profiles", "onboarding_step"}
        )
        restored = ChatSettings.model_validate_json(old_json)
        assert restored.profiles == {}
        assert restored.onboarding_step is None

    def test_legacy_single_profile_json_migrates_to_laundry_key(self) -> None:
        # Pre-5D JSON shape: a top-level "profile" object, no "profiles" dict.
        legacy_json = (
            '{"chat_id": 1, "language": "en", '
            '"profile": {"target_per_week": 3, "timezone": "Europe/London"}, '
            '"onboarding_step": null, "enabled_tasks": ["laundry"], '
            f'"updated_at": "{_NOW.isoformat()}"}}'
        )
        restored = ChatSettings.model_validate_json(legacy_json)
        assert restored.profiles == {
            "laundry": TaskProfile(target_per_week=3, timezone="Europe/London")
        }

    def test_legacy_null_profile_json_migrates_to_empty_dict(self) -> None:
        legacy_json = (
            '{"chat_id": 1, "language": "en", "profile": null, '
            '"onboarding_step": null, "enabled_tasks": ["laundry"], '
            f'"updated_at": "{_NOW.isoformat()}"}}'
        )
        restored = ChatSettings.model_validate_json(legacy_json)
        assert restored.profiles == {}

    def test_migration_validator_passes_through_non_dict_instance_input(self) -> None:
        # model_validate() on an already-constructed instance (e.g. during a
        # revalidating model_copy) passes a ChatSettings, not a dict, to the
        # before-validator — it must pass through rather than error.
        original = ChatSettings(chat_id=1, updated_at=_NOW)
        revalidated = ChatSettings.model_validate(original)
        assert revalidated == original

    def test_migration_is_idempotent_for_already_migrated_json(self) -> None:
        original = ChatSettings(
            chat_id=1, profiles={"laundry": TaskProfile(target_per_week=4)}, updated_at=_NOW
        )
        once = ChatSettings.model_validate_json(original.model_dump_json())
        twice = ChatSettings.model_validate_json(once.model_dump_json())
        assert once == original
        assert twice == original

    def test_effective_timezone_none_when_no_profiles(self) -> None:
        settings = ChatSettings(chat_id=1, updated_at=_NOW)
        assert settings.effective_timezone is None

    def test_effective_timezone_prefers_laundry_profile(self) -> None:
        settings = ChatSettings(
            chat_id=1,
            profiles={
                "laundry": TaskProfile(timezone="Europe/London"),
                "dishwasher": TaskProfile(timezone="Asia/Hong_Kong"),
            },
            updated_at=_NOW,
        )
        assert settings.effective_timezone == "Europe/London"

    def test_effective_timezone_falls_back_to_other_profile(self) -> None:
        settings = ChatSettings(
            chat_id=1,
            profiles={
                "laundry": TaskProfile(),  # no timezone set
                "dishwasher": TaskProfile(timezone="Asia/Hong_Kong"),
            },
            updated_at=_NOW,
        )
        assert settings.effective_timezone == "Asia/Hong_Kong"


# ---------------------------------------------------------------------------
# TaskProfile — Sprint 5B
# ---------------------------------------------------------------------------


class TestTaskProfile:
    def test_all_defaults_are_valid(self) -> None:
        profile = TaskProfile()
        assert profile.target_per_week == 2
        assert profile.duration_slots == 4
        assert profile.outdoor_drying is True
        assert profile.timezone is None

    def test_is_frozen(self) -> None:
        profile = TaskProfile()
        with pytest.raises(ValidationError):
            profile.target_per_week = 5  # type: ignore[misc]

    def test_invalid_hhmm_rejected(self) -> None:
        with pytest.raises(ValidationError, match="HH:MM"):
            TaskProfile(earliest_start="not-a-time")

    def test_finish_before_start_rejected(self) -> None:
        with pytest.raises(ValidationError, match="latest_finish must be after earliest_start"):
            TaskProfile(earliest_start="20:00", latest_finish="08:00")

    def test_target_below_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TaskProfile(target_per_week=0)

    def test_legacy_laundry_target_per_week_alias_still_accepted(self) -> None:
        # Backward-compat for old code/JSON using the pre-5D field name.
        profile = TaskProfile(laundry_target_per_week=6)
        assert profile.target_per_week == 6

    def test_max_rain_probability_out_of_bounds_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TaskProfile(max_rain_probability=101)

    def test_valid_iana_timezone_accepted(self) -> None:
        profile = TaskProfile(timezone="Europe/London")
        assert profile.timezone == "Europe/London"

    def test_none_timezone_accepted(self) -> None:
        profile = TaskProfile(timezone=None)
        assert profile.timezone is None

    def test_invalid_timezone_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown IANA timezone"):
            TaskProfile(timezone="Mars/Colony_One")


# ---------------------------------------------------------------------------
# i18n catalogue
# ---------------------------------------------------------------------------


class TestCatalogueCompleteness:
    @pytest.mark.parametrize("key", list(MessageKey))
    def test_every_key_has_every_language(self, key: MessageKey) -> None:
        assert set(_CATALOGUE[key]) == set(Language)

    def test_no_orphan_catalogue_entries(self) -> None:
        assert set(_CATALOGUE) == set(MessageKey)


class TestT:
    def test_formats_kwargs(self) -> None:
        text = t(MessageKey.HEALTH_OK, Language.EN, version="9.9.9")
        assert "9.9.9" in text

    def test_zh_variant_differs_from_en(self) -> None:
        en = t(MessageKey.NO_EVENTS, Language.EN)
        zh = t(MessageKey.NO_EVENTS, Language.ZH)
        assert en != zh

    def test_missing_kwarg_raises(self) -> None:
        with pytest.raises(KeyError):
            t(MessageKey.HEALTH_OK, Language.EN)


class TestBilingualWelcome:
    def test_contains_both_languages(self) -> None:
        text = bilingual_welcome()
        assert "Hello" in text
        assert "你好" in text

    def test_lists_prices_command(self) -> None:
        assert "/prices" in bilingual_welcome()

    def test_contains_language_prompt(self) -> None:
        assert "choose your language" in bilingual_welcome()
