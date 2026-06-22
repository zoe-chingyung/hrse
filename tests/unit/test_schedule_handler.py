"""Unit tests for the schedule Lambda handler."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hrse.handlers.schedule_handler import handler


@pytest.mark.unit()
class TestScheduleHandler:
    """Smoke-test the handler stub — will grow as services are implemented."""

    def _context(self) -> MagicMock:
        ctx = MagicMock()
        ctx.function_name = "hrse-schedule-handler"
        ctx.aws_request_id = "test-request-id"
        ctx.invoked_function_arn = "arn:aws:lambda:eu-west-2:123456789012:function:hrse"
        return ctx

    def _event(self) -> dict:
        return {
            "source": "hrse.scheduler",
            "detail-type": "ScheduleRequest",
            "detail": {},
        }

    def test_returns_200(self) -> None:
        response = handler(self._event(), self._context())
        assert response["statusCode"] == 200

    def test_body_is_json_string(self) -> None:
        import json

        response = handler(self._event(), self._context())
        body = json.loads(response["body"])
        assert "message" in body
