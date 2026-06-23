"""Unit tests for S3EventStore.

Uses moto to simulate S3 — no real AWS calls.
All tests depend on the ``s3_bucket`` fixture which creates and tears down
the bucket automatically.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import boto3
import pytest
from moto import mock_aws

from hrse.models.events import LAUNDRY_COMPLETED, Event
from hrse.store.s3_store import S3EventStore

_BUCKET = "hrse-test-state"
_REGION = "eu-west-2"


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
def store(s3_bucket) -> S3EventStore:  # noqa: ANN001
    """Return an ``S3EventStore`` pointing at the moto bucket."""
    return S3EventStore(bucket_name=_BUCKET, region_name=_REGION)


# ---------------------------------------------------------------------------
# Empty store
# ---------------------------------------------------------------------------


@pytest.mark.integration()
class TestEmptyStore:
    def test_list_events_returns_empty_list(self, store: S3EventStore) -> None:
        assert store.list_events() == []

    def test_list_events_twice_still_empty(self, store: S3EventStore) -> None:
        assert store.list_events() == []
        assert store.list_events() == []


# ---------------------------------------------------------------------------
# Append event
# ---------------------------------------------------------------------------


@pytest.mark.integration()
class TestAppendEvent:
    def _event(self, event_type: str = LAUNDRY_COMPLETED) -> Event:
        return Event(
            event_type=event_type,
            timestamp=datetime(2026, 6, 23, 18, 30, 0, tzinfo=UTC),
        )

    def test_appended_event_returned_by_list(self, store: S3EventStore) -> None:
        store.append_event(self._event())
        events = store.list_events()
        assert len(events) == 1
        assert events[0].event_type == LAUNDRY_COMPLETED

    def test_timestamp_preserved(self, store: S3EventStore) -> None:
        ts = datetime(2026, 6, 23, 18, 30, 0, tzinfo=UTC)
        store.append_event(Event(event_type=LAUNDRY_COMPLETED, timestamp=ts))
        assert store.list_events()[0].timestamp == ts

    def test_multiple_events_ordered_oldest_first(self, store: S3EventStore) -> None:
        t1 = datetime(2026, 6, 23, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 6, 23, 11, 0, 0, tzinfo=UTC)
        store.append_event(Event(event_type=LAUNDRY_COMPLETED, timestamp=t1))
        store.append_event(Event(event_type=LAUNDRY_COMPLETED, timestamp=t2))
        events = store.list_events()
        assert events[0].timestamp == t1
        assert events[1].timestamp == t2

    def test_events_persisted_across_store_instances(self, s3_bucket) -> None:  # noqa: ANN001
        """Two separate store instances sharing the same bucket stay in sync."""
        store_a = S3EventStore(bucket_name=_BUCKET, region_name=_REGION)
        store_b = S3EventStore(bucket_name=_BUCKET, region_name=_REGION)

        store_a.append_event(self._event())
        assert len(store_b.list_events()) == 1

    def test_json_stored_correctly(self, store: S3EventStore) -> None:
        """The S3 object must contain valid JSON with the correct shape."""
        ts = datetime(2026, 6, 23, 18, 30, 0, tzinfo=UTC)
        store.append_event(Event(event_type=LAUNDRY_COMPLETED, timestamp=ts))

        client = boto3.client("s3", region_name=_REGION)
        obj = client.get_object(Bucket=_BUCKET, Key="events/household_events.json")
        data = json.loads(obj["Body"].read())

        assert isinstance(data, list)
        assert data[0]["event_type"] == LAUNDRY_COMPLETED
        assert "timestamp" in data[0]
