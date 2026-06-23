"""S3-backed implementation of EventStore.

Storage layout
--------------
Bucket  : configured via ``HRSE_STATE_BUCKET_NAME``
Key     : ``events/household_events.json``
Format  : JSON array, one object per event, oldest first.

    [
      {"event_type": "laundry_completed", "timestamp": "2026-06-23T18:30:00.000Z"},
      ...
    ]

Read-modify-write
-----------------
Each ``append_event`` call:
  1. Downloads the current array (empty list if the key does not exist).
  2. Appends the new event.
  3. Uploads the updated array.

This is safe for the current single-Lambda invocation model. If concurrent
writes become a concern in future sprints, replace with a DynamoDB-backed
store or add conditional puts with ETags.

Replacing this backend
----------------------
Swap out ``S3EventStore`` for any class that satisfies ``EventStore`` at the
factory level (``get_event_store``). Nothing else in the application changes.
"""

from __future__ import annotations

import json
from functools import lru_cache

import boto3
from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError

from hrse.models.events import Event

logger = Logger(child=True)

_EVENTS_KEY = "events/household_events.json"


class S3EventStore:
    """Stores events as a JSON array in an S3 object.

    Args:
        bucket_name: The S3 bucket to read from and write to.
        region_name: AWS region of the bucket.
    """

    def __init__(self, bucket_name: str, region_name: str = "eu-west-2") -> None:
        self._bucket = bucket_name
        self._client = boto3.client("s3", region_name=region_name)

    # ------------------------------------------------------------------
    # EventStore implementation
    # ------------------------------------------------------------------

    def append_event(self, event: Event) -> None:
        """Append ``event`` to the JSON array stored in S3.

        Args:
            event: The event to persist.
        """
        events = self._load()
        events.append(event)
        self._save(events)
        logger.info(
            "Event appended",
            extra={"event_type": event.event_type, "bucket": self._bucket},
        )

    def list_events(self) -> list[Event]:
        """Return all stored events, oldest first.

        Returns:
            List of ``Event`` objects. Empty list if none stored yet.
        """
        return self._load()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load(self) -> list[Event]:
        """Download and deserialise the events JSON from S3."""
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=_EVENTS_KEY)
            raw: list[dict] = json.loads(response["Body"].read())
            return [Event.model_validate(item) for item in raw]
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "NoSuchKey":
                logger.debug("No events file found in S3; starting with empty list")
                return []
            raise

    def _save(self, events: list[Event]) -> None:
        """Serialise and upload the events list to S3."""
        body = json.dumps(
            [
                {
                    "event_type": e.event_type,
                    "timestamp": e.timestamp.isoformat().replace("+00:00", "Z"),
                }
                for e in events
            ],
            indent=2,
        ).encode()
        self._client.put_object(
            Bucket=self._bucket,
            Key=_EVENTS_KEY,
            Body=body,
            ContentType="application/json",
        )
        logger.debug("Events saved to S3", extra={"count": len(events), "bucket": self._bucket})


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_event_store() -> S3EventStore:
    """Return a cached ``S3EventStore`` wired from application settings.

    Called once per Lambda container lifetime.
    Call ``get_event_store.cache_clear()`` in tests to reset.
    """
    from hrse.config import get_settings

    settings = get_settings()
    return S3EventStore(
        bucket_name=settings.state_bucket_name,
        region_name=settings.aws_region,
    )
