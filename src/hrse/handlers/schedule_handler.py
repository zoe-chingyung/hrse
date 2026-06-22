"""Lambda handler for schedule lifecycle events.

Entry point: ``hrse.handlers.schedule_handler.handler``

Event contract (EventBridge → Lambda):
    {
        "source": "hrse.scheduler",
        "detail-type": "ScheduleRequest",
        "detail": { ... }   # validated against ScheduleRequestEvent
    }

No business logic lives here — handlers are thin adapters that
validate input, delegate to a service, and format the response.
"""

from __future__ import annotations

import json
from typing import Any

from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

from hrse.config import get_settings

logger = Logger()
tracer = Tracer()


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Main Lambda entry point for schedule requests.

    Args:
        event: The Lambda invocation event (EventBridge schema).
        context: Lambda runtime context.

    Returns:
        A dict serialisable to JSON with at minimum ``statusCode`` and ``body``.
    """
    settings = get_settings()
    logger.info("Received event", extra={"detail_type": event.get("detail-type")})
    logger.debug("Settings", extra={"region": settings.aws_region})

    # TODO (Sprint 2): parse event.detail into ScheduleRequestEvent,
    #                  call ScheduleService, persist to DynamoDB.

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "handler stub – not yet implemented"}),
    }
