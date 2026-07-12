"""Unit tests for ChatSettingsStore implementations.

Uses moto to simulate S3 — no real AWS calls.
"""

from __future__ import annotations

from datetime import UTC, datetime

import boto3
import pytest
from moto import mock_aws

from hrse.models.chat_settings import ChatSettings, Language
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
