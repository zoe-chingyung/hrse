"""Unit tests for the Octopus Agile client.

The HTTP implementation is tested by mocking ``urllib.request.urlopen`` so no
real network call is made. A protocol-satisfying in-memory stub is also
provided for use by downstream tests (e.g. the decision engine).
"""

from __future__ import annotations

import io
import json
import urllib.error
from datetime import UTC, datetime
from typing import Any

import pytest

from hrse.clients.octopus import (
    HttpOctopusClient,
    OctopusApiError,
    OctopusClientProtocol,
    get_octopus_client,
)
from hrse.models.pricing import PricePoint

# ---------------------------------------------------------------------------
# In-memory stub — satisfies OctopusClientProtocol without any network
# ---------------------------------------------------------------------------


class StubOctopusClient:
    """Returns a fixed list of prices regardless of the requested range."""

    def __init__(self, prices: list[PricePoint] | None = None) -> None:
        self._prices = list(prices or [])

    def get_prices(self, period_from: datetime, period_to: datetime) -> list[PricePoint]:
        return list(self._prices)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_response(payload: dict[str, Any]) -> io.BytesIO:
    """Build a context-manager-capable fake HTTP response body."""

    class _Resp(io.BytesIO):
        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *args: object) -> None:
            self.close()

    return _Resp(json.dumps(payload).encode())


def _client() -> HttpOctopusClient:
    return HttpOctopusClient(
        product_code="AGILE-24-10-01",
        tariff_code="E-1R-AGILE-24-10-01-A",
    )


# ---------------------------------------------------------------------------
# Stub tests
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestStubSatisfiesProtocol:
    def test_stub_is_protocol_instance(self) -> None:
        stub = StubOctopusClient()
        assert isinstance(stub, OctopusClientProtocol)

    def test_stub_returns_supplied_prices(self) -> None:
        pts = [PricePoint(timestamp=datetime(2026, 6, 23, 12, 0, tzinfo=UTC), price_pence=8.4)]
        stub = StubOctopusClient(pts)
        result = stub.get_prices(
            datetime(2026, 6, 23, tzinfo=UTC), datetime(2026, 6, 24, tzinfo=UTC)
        )
        assert result == pts


# ---------------------------------------------------------------------------
# HTTP client tests (mocked urlopen)
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestHttpOctopusClientParsing:
    def test_parses_results_into_pricepoints(self, mocker: Any) -> None:
        payload = {
            "count": 2,
            "next": None,
            "previous": None,
            "results": [
                {
                    "value_exc_vat": 8.0,
                    "value_inc_vat": 8.4,
                    "valid_from": "2026-06-23T12:30:00Z",
                    "valid_to": "2026-06-23T13:00:00Z",
                },
                {
                    "value_exc_vat": 6.0,
                    "value_inc_vat": 6.3,
                    "valid_from": "2026-06-23T12:00:00Z",
                    "valid_to": "2026-06-23T12:30:00Z",
                },
            ],
        }
        mocker.patch("urllib.request.urlopen", return_value=_fake_response(payload))

        prices = _client().get_prices(
            datetime(2026, 6, 23, 12, 0, tzinfo=UTC),
            datetime(2026, 6, 23, 13, 0, tzinfo=UTC),
        )

        assert len(prices) == 2
        assert prices[0].price_pence == 6.3  # uses value_inc_vat
        assert prices[0].timestamp < prices[1].timestamp  # sorted oldest-first

    def test_empty_results_returns_empty_list(self, mocker: Any) -> None:
        payload = {"count": 0, "next": None, "previous": None, "results": []}
        mocker.patch("urllib.request.urlopen", return_value=_fake_response(payload))
        assert (
            _client().get_prices(
                datetime(2026, 6, 23, tzinfo=UTC), datetime(2026, 6, 24, tzinfo=UTC)
            )
            == []
        )


@pytest.mark.unit()
class TestHttpOctopusClientRequest:
    def test_request_targets_correct_url_with_iso_params(self, mocker: Any) -> None:
        payload = {"results": []}
        fake_open = mocker.patch("urllib.request.urlopen", return_value=_fake_response(payload))

        _client().get_prices(
            datetime(2026, 6, 23, 0, 0, tzinfo=UTC),
            datetime(2026, 6, 24, 0, 0, tzinfo=UTC),
        )

        request = fake_open.call_args.args[0]
        url = request.full_url
        assert "/v1/products/AGILE-24-10-01/electricity-tariffs/" in url
        assert "E-1R-AGILE-24-10-01-A/standard-unit-rates/" in url
        assert "period_from=2026-06-23T00%3A00%3A00.000Z" in url
        assert "period_to=2026-06-24T00%3A00%3A00.000Z" in url
        assert request.method == "GET"


@pytest.mark.unit()
class TestHttpOctopusClientErrors:
    def test_http_error_raises_octopus_api_error(self, mocker: Any) -> None:
        err = urllib.error.HTTPError(
            url="http://x", code=404, msg="Not Found", hdrs=None, fp=io.BytesIO(b'{"detail":"no"}')
        )
        mocker.patch("urllib.request.urlopen", side_effect=err)

        with pytest.raises(OctopusApiError) as exc_info:
            _client().get_prices(
                datetime(2026, 6, 23, tzinfo=UTC), datetime(2026, 6, 24, tzinfo=UTC)
            )
        assert exc_info.value.status_code == 404

    def test_malformed_payload_raises(self, mocker: Any) -> None:
        mocker.patch("urllib.request.urlopen", return_value=_fake_response({"unexpected": True}))
        with pytest.raises(OctopusApiError):
            _client().get_prices(
                datetime(2026, 6, 23, tzinfo=UTC), datetime(2026, 6, 24, tzinfo=UTC)
            )

    def test_malformed_record_raises(self, mocker: Any) -> None:
        payload = {"results": [{"valid_from": "2026-06-23T12:00:00Z"}]}  # missing price
        mocker.patch("urllib.request.urlopen", return_value=_fake_response(payload))
        with pytest.raises(OctopusApiError):
            _client().get_prices(
                datetime(2026, 6, 23, tzinfo=UTC), datetime(2026, 6, 24, tzinfo=UTC)
            )


@pytest.mark.unit()
class TestFactory:
    def test_factory_returns_client_from_settings(self) -> None:
        get_octopus_client.cache_clear()
        client = get_octopus_client()
        assert isinstance(client, HttpOctopusClient)
        get_octopus_client.cache_clear()
