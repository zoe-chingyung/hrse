"""Octopus Agile electricity-price client.

Design
------
* ``OctopusClientProtocol`` — structural typing contract used by the decision
  engine and in tests (no concrete dependency required).
* ``HttpOctopusClient`` — production implementation that calls the public
  Octopus Energy REST API over HTTPS using the standard library ``urllib``
  (no extra dependency, matching the Telegram client).
* ``get_octopus_client`` — factory that wires the real client from settings.
  Call once at Lambda cold-start and reuse.

API reference
-------------
Endpoint (no authentication required for Agile unit rates)::

    GET /v1/products/{product_code}/electricity-tariffs/{tariff_code}
        /standard-unit-rates/?period_from=...&period_to=...&page_size=...

Response shape::

    {
      "count": 48,
      "next": null,
      "previous": null,
      "results": [
        {
          "value_exc_vat": 8.4,
          "value_inc_vat": 8.82,
          "valid_from": "2026-06-23T12:00:00Z",
          "valid_to": "2026-06-23T12:30:00Z"
        },
        ...
      ]
    }

We use ``value_inc_vat`` (the price a household actually pays) and
``valid_from`` (the UTC start of the 30-minute settlement period).
``period_from``/``period_to`` must be ISO 8601 with a trailing ``Z``.

Dependency injection
--------------------
The decision engine accepts an ``OctopusClientProtocol`` so tests can pass a
lightweight stub without touching the network.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime  # noqa: TCH003 — used in method signatures at runtime
from functools import lru_cache
from typing import Any, Protocol, runtime_checkable

from aws_lambda_powertools import Logger

from hrse.models.pricing import PricePoint
from hrse.utils.datetime_utils import to_iso8601

logger = Logger(child=True)

_OCTOPUS_API_BASE = "https://api.octopus.energy"
# Max half-hour periods Octopus returns per page; 1500 ≈ one month of Agile data.
_MAX_PAGE_SIZE = 1500


# ---------------------------------------------------------------------------
# Protocol (interface)
# ---------------------------------------------------------------------------


@runtime_checkable
class OctopusClientProtocol(Protocol):
    """Structural contract for anything that can fetch Agile prices.

    Using a Protocol (instead of ABC) means test doubles just need to
    implement the right method — no inheritance required.
    """

    def get_prices(self, period_from: datetime, period_to: datetime) -> list[PricePoint]:
        """Fetch half-hourly prices for the given UTC time range.

        Args:
            period_from: Inclusive UTC start of the range.
            period_to:   Exclusive UTC end of the range.

        Returns:
            A list of ``PricePoint`` sorted oldest-first.

        Raises:
            OctopusApiError: If the API returns a non-2xx response.
        """
        ...


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class OctopusApiError(Exception):
    """Raised when the Octopus API returns an error response."""

    def __init__(self, status_code: int, description: str) -> None:
        self.status_code = status_code
        self.description = description
        super().__init__(f"Octopus API error {status_code}: {description}")


# ---------------------------------------------------------------------------
# Production implementation
# ---------------------------------------------------------------------------


class HttpOctopusClient:
    """Fetches Agile prices from the Octopus Energy REST API via HTTPS.

    Uses ``urllib`` from the standard library to avoid adding an HTTP client
    dependency to the Lambda package.

    Args:
        product_code: Octopus product code, e.g. "AGILE-24-10-01".
        tariff_code:  Regional tariff code, e.g. "E-1R-AGILE-24-10-01-A".
    """

    def __init__(self, product_code: str, tariff_code: str) -> None:
        self._product_code = product_code
        self._tariff_code = tariff_code

    # ------------------------------------------------------------------
    # OctopusClientProtocol implementation
    # ------------------------------------------------------------------

    def get_prices(self, period_from: datetime, period_to: datetime) -> list[PricePoint]:
        """GET ``standard-unit-rates`` for the given range and parse to PricePoints.

        Args:
            period_from: Inclusive UTC start of the range.
            period_to:   Exclusive UTC end of the range.

        Returns:
            ``PricePoint`` list sorted oldest-first.

        Raises:
            OctopusApiError: On a non-2xx response or malformed payload.
        """
        query = urllib.parse.urlencode(
            {
                "period_from": to_iso8601(period_from),
                "period_to": to_iso8601(period_to),
                "page_size": _MAX_PAGE_SIZE,
            }
        )
        url = (
            f"{_OCTOPUS_API_BASE}/v1/products/{self._product_code}"
            f"/electricity-tariffs/{self._tariff_code}/standard-unit-rates/?{query}"
        )

        logger.debug(
            "Fetching Octopus prices",
            extra={"product": self._product_code, "tariff": self._tariff_code},
        )

        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req) as resp:  # noqa: S310 (url built from our config)
                body: dict[str, Any] = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                parsed = json.loads(raw)
                description = parsed.get("detail", str(exc))
            except (json.JSONDecodeError, AttributeError):
                description = raw.decode(errors="replace")
            raise OctopusApiError(exc.code, description) from exc

        points = self._parse_results(body)
        logger.info("Fetched Octopus prices", extra={"count": len(points)})
        return points

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_results(body: dict[str, Any]) -> list[PricePoint]:
        """Convert the API ``results`` array into sorted ``PricePoint`` objects.

        Args:
            body: The decoded JSON response.

        Returns:
            ``PricePoint`` list sorted oldest-first by timestamp.

        Raises:
            OctopusApiError: If ``results`` is missing or malformed.
        """
        results = body.get("results")
        if not isinstance(results, list):
            raise OctopusApiError(0, "malformed response: 'results' missing or not a list")

        points: list[PricePoint] = []
        for item in results:
            try:
                points.append(
                    PricePoint(
                        timestamp=datetime.fromisoformat(item["valid_from"]),
                        price_pence=float(item["value_inc_vat"]),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise OctopusApiError(0, f"malformed price record: {item!r}") from exc

        points.sort(key=lambda p: p.timestamp)
        return points


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_octopus_client() -> HttpOctopusClient:
    """Return a cached ``HttpOctopusClient`` wired from application settings.

    Called once per Lambda container lifetime.
    Call ``get_octopus_client.cache_clear()`` in tests to reset.
    """
    from hrse.config import get_settings

    settings = get_settings()
    return HttpOctopusClient(
        product_code=settings.octopus_product_code,
        tariff_code=settings.octopus_tariff_code,
    )
