"""Unit tests for SecretsManagerTokenProvider."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from hrse.telegram.token_provider import SecretsManagerTokenProvider


class TestSecretsManagerTokenProvider:
    """Token fetching, caching, and error handling."""

    def _provider(self) -> SecretsManagerTokenProvider:
        return SecretsManagerTokenProvider(
            secret_name="hrse/dev/telegram",
            region_name="eu-west-2",
        )

    def _mock_boto_client(self, token: str = "test-token-123") -> MagicMock:
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps({"bot_token": token})
        }
        return mock_client

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    @patch("hrse.telegram.token_provider.boto3.client")
    def test_returns_bot_token(self, mock_boto: MagicMock) -> None:
        mock_boto.return_value = self._mock_boto_client("abc123")
        provider = self._provider()
        assert provider() == "abc123"

    @patch("hrse.telegram.token_provider.boto3.client")
    def test_uses_correct_secret_name(self, mock_boto: MagicMock) -> None:
        mock_client = self._mock_boto_client()
        mock_boto.return_value = mock_client
        provider = self._provider()
        provider()
        mock_client.get_secret_value.assert_called_once_with(SecretId="hrse/dev/telegram")

    @patch("hrse.telegram.token_provider.boto3.client")
    def test_uses_eu_west_2_region(self, mock_boto: MagicMock) -> None:
        mock_boto.return_value = self._mock_boto_client()
        provider = self._provider()
        provider()
        mock_boto.assert_called_once_with("secretsmanager", region_name="eu-west-2")

    # ------------------------------------------------------------------
    # Caching
    # ------------------------------------------------------------------

    @patch("hrse.telegram.token_provider.boto3.client")
    def test_token_cached_after_first_call(self, mock_boto: MagicMock) -> None:
        mock_client = self._mock_boto_client()
        mock_boto.return_value = mock_client
        provider = self._provider()

        provider()
        provider()
        provider()

        # Secrets Manager must be called exactly once per provider lifetime.
        mock_client.get_secret_value.assert_called_once()

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    @patch("hrse.telegram.token_provider.boto3.client")
    def test_invalid_json_raises_value_error(self, mock_boto: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {"SecretString": "not-json"}
        mock_boto.return_value = mock_client

        with pytest.raises(ValueError, match="not valid JSON"):
            self._provider()()

    @patch("hrse.telegram.token_provider.boto3.client")
    def test_missing_bot_token_key_raises_key_error(self, mock_boto: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps({"other_key": "value"})
        }
        mock_boto.return_value = mock_client

        with pytest.raises(KeyError, match="bot_token"):
            self._provider()()
