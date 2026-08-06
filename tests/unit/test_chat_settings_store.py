"""Unit tests for ChatSettingsStore implementations.

Uses moto to simulate S3 — no real AWS calls.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws

from hrse.models.chat_settings import ChatSettings, Language, TaskProfile
from hrse.store.chat_settings_store import (
    InMemoryChatSettingsStore,
    S3ChatSettingsStore,
    get_chat_settings_store,
)

_BUCKET = "hrse-test-state"
_REGION = "eu-west-2"

_NOW = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def s3_bucket(aws_credentials):  # noqa: ANN001 — aws_credentials sets env vars
    """Create a real moto-backed S3 bucket for the duration of each test."""
    with mock_aws():
        client = boto3.client("s3", region_name=_REGION)
        client.create_bucket(
            Bucket=_BUCKET,
            CreateBucketConfiguration={"LocationConstraint": _REGION},
        )
        yield


@pytest.fixture()
def store(s3_bucket) -> S3ChatSettingsStore:  # noqa: ANN001
    """Return an ``S3ChatSettingsStore`` pointing at the moto bucket."""
    return S3ChatSettingsStore(bucket_name=_BUCKET, region_name=_REGION)


def _settings(chat_id: int = -100, lang: Language = Language.ZH) -> ChatSettings:
    return ChatSettings(chat_id=chat_id, language=lang, updated_at=_NOW)


# ---------------------------------------------------------------------------
# S3ChatSettingsStore
# ---------------------------------------------------------------------------


@pytest.mark.integration()
class TestS3ChatSettingsStore:
    def test_get_unknown_chat_returns_none(self, store: S3ChatSettingsStore) -> None:
        assert store.get(999) is None

    def test_save_then_get_round_trips(self, store: S3ChatSettingsStore) -> None:
        store.save(_settings())
        assert store.get(-100) == _settings()

    def test_save_overwrites_previous_value(self, store: S3ChatSettingsStore) -> None:
        store.save(_settings(lang=Language.EN))
        store.save(_settings(lang=Language.ZH))
        loaded = store.get(-100)
        assert loaded is not None
        assert loaded.language is Language.ZH

    def test_chats_are_isolated(self, store: S3ChatSettingsStore) -> None:
        store.save(_settings(chat_id=-1, lang=Language.ZH))
        store.save(_settings(chat_id=2, lang=Language.EN))
        loaded_group = store.get(-1)
        loaded_private = store.get(2)
        assert loaded_group is not None and loaded_group.language is Language.ZH
        assert loaded_private is not None and loaded_private.language is Language.EN

    def test_object_stored_under_settings_prefix(self, store: S3ChatSettingsStore) -> None:
        store.save(_settings(chat_id=-42))
        client = boto3.client("s3", region_name=_REGION)
        keys = [o["Key"] for o in client.list_objects_v2(Bucket=_BUCKET)["Contents"]]
        assert keys == ["settings/-42.json"]

    def test_round_trip_with_full_profile(self, store: S3ChatSettingsStore) -> None:
        original = ChatSettings(
            chat_id=-7,
            language=Language.ZH,
            profiles={
                "laundry": TaskProfile(
                    target_per_week=3,
                    earliest_start="07:00",
                    latest_finish="21:00",
                    outdoor_drying=False,
                    timezone="Asia/Hong_Kong",
                )
            },
            onboarding_step=None,
            updated_at=_NOW,
        )
        store.save(original)
        assert store.get(-7) == original

    def test_round_trip_with_two_task_profiles(self, store: S3ChatSettingsStore) -> None:
        original = ChatSettings(
            chat_id=-8,
            profiles={
                "laundry": TaskProfile(target_per_week=3, timezone="Europe/London"),
                "ev": TaskProfile(target_per_week=2, wash_budget_pence=150.0),
            },
            enabled_tasks=["laundry", "ev"],
            updated_at=_NOW,
        )
        store.save(original)
        assert store.get(-8) == original

    def test_legacy_single_profile_json_loads_via_s3(self, store: S3ChatSettingsStore) -> None:
        # Simulates an S3 object written by pre-5D code — no "profiles" key.
        client = boto3.client("s3", region_name=_REGION)
        legacy_body = (
            '{"chat_id": -9, "language": "en", '
            '"profile": {"target_per_week": 4}, "onboarding_step": null, '
            '"enabled_tasks": ["laundry"], "updated_at": "2026-07-12T10:00:00Z"}'
        )
        client.put_object(Bucket=_BUCKET, Key="settings/-9.json", Body=legacy_body.encode())

        loaded = store.get(-9)
        assert loaded is not None
        assert loaded.profiles == {"laundry": TaskProfile(target_per_week=4)}

    @pytest.mark.integration()
    def test_list_all_chat_ids_returns_all_stored_chats(self, store: S3ChatSettingsStore) -> None:
        store.save(_settings(chat_id=1))
        store.save(_settings(chat_id=-2))
        store.save(_settings(chat_id=3))
        assert sorted(store.list_all_chat_ids()) == [-2, 1, 3]

    @pytest.mark.integration()
    def test_list_all_chat_ids_empty_bucket(self, store: S3ChatSettingsStore) -> None:
        assert store.list_all_chat_ids() == []

    @pytest.mark.integration()
    def test_list_all_chat_ids_ignores_malformed_keys(self, store: S3ChatSettingsStore) -> None:
        store.save(_settings(chat_id=1))
        client = boto3.client("s3", region_name=_REGION)
        client.put_object(Bucket=_BUCKET, Key="settings/not-an-int.json", Body=b"{}")
        client.put_object(Bucket=_BUCKET, Key="settings/2.txt", Body=b"{}")
        client.put_object(Bucket=_BUCKET, Key="settings/", Body=b"")
        assert store.list_all_chat_ids() == [1]

    def test_list_all_chat_ids_paginates(self, store: S3ChatSettingsStore) -> None:
        # Exercise the pagination loop directly via a mocked client/paginator
        # rather than creating 1000+ real moto objects.
        mock_client = MagicMock()
        paginator = MagicMock()
        mock_client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {"Contents": [{"Key": "settings/1.json"}, {"Key": "settings/2.json"}]},
            {"Contents": [{"Key": "settings/3.json"}]},
        ]
        store._client = mock_client  # noqa: SLF001 — test injects a mocked boto3 client

        assert sorted(store.list_all_chat_ids()) == [1, 2, 3]
        mock_client.get_paginator.assert_called_once_with("list_objects_v2")
        paginator.paginate.assert_called_once_with(Bucket=_BUCKET, Prefix="settings/")


# ---------------------------------------------------------------------------
# InMemoryChatSettingsStore
# ---------------------------------------------------------------------------


class TestInMemoryChatSettingsStore:
    def test_get_unknown_chat_returns_none(self) -> None:
        assert InMemoryChatSettingsStore().get(1) is None

    def test_save_then_get_round_trips(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_settings())
        assert store.get(-100) == _settings()

    def test_list_all_chat_ids_returns_all_stored_chats(self) -> None:
        store = InMemoryChatSettingsStore()
        store.save(_settings(chat_id=1))
        store.save(_settings(chat_id=-2))
        assert sorted(store.list_all_chat_ids()) == [-2, 1]

    def test_list_all_chat_ids_empty_store(self) -> None:
        assert InMemoryChatSettingsStore().list_all_chat_ids() == []


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestFactory:
    def test_factory_returns_cached_instance(self, aws_credentials) -> None:  # noqa: ANN001
        get_chat_settings_store.cache_clear()
        try:
            first = get_chat_settings_store()
            second = get_chat_settings_store()
            assert first is second
        finally:
            get_chat_settings_store.cache_clear()
