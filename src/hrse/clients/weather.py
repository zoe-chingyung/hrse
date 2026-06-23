"""Weather forecast client (Open-Meteo).

Design
------
* ``WeatherClientProtocol`` — structural typing contract used by the decision
  engine and in tests (no concrete dependency required).
* ``HttpWeatherClient`` — production implementation that calls the public
  Open-Meteo forecast API over HTTPS using the standard library ``urllib``
  (no extra dependency, matching the Telegram and Octopus clients).
* ``get_weather_client`` — factory that wires the real client from settings.
  Call once at Lambda cold-start and reuse.

API reference
-------------
Open-Meteo needs no API key and is free for non-commercial use. Endpoint::

    GET https://api.open-meteo.com/v1/forecast
        ?latitude=...&longitude=...
        &daily=temperature_2m_max,uv_index_max,precipitation_probability_max
        &timezone=UTC&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD

Response shape (daily arrays are parallel, indexed by the ``time`` array)::

    {
      "latitude": 51.5,
      "longitude": -0.1,
      "daily": {
        "time": ["2026-06-23"],
        "temperature_2m_max": [27.0],
        "uv_index_max": [7.0],
        "precipitation_probability_max": [10]
      },
      "daily_units": {...}
    }

On error, Open-Meteo returns HTTP 400 with ``{"error": true, "reason": "..."}``.

Dependency injection
--------------------
The decision engine accepts a ``WeatherClientProtocol`` so tests can pass a
lightweight stub without touching the network.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date  # noqa: TCH003 — used in method signatures at runtime
from functools import lru_cache
from typing import Any, Protocol, runtime_checkable

from aws_lambda_powertools import Logger

from hrse.models.weather import DailyForecast

logger = Logger(child=True)

_OPEN_METEO_BASE = "https://api.open-meteo.com"
_DAILY_VARS = "temperature_2m_max,uv_index_max,precipitation_probability_max"


# ---------------------------------------------------------------------------
# Protocol (interface)
# ---------------------------------------------------------------------------


@runtime_checkable
class WeatherClientProtocol(Protocol):
    """Structural contract for anything that can fetch a daily forecast.

    Using a Protocol (instead of ABC) means test doubles just need to
    implement the right method — no inheritance required.
    """

    def get_forecast(self, target_date: date) -> DailyForecast:
        """Fetch the daily weather summary for ``target_date``.

        Args:
            target_date: The calendar date to forecast.

        Returns:
            A populated ``DailyForecast``.

        Raises:
            WeatherApiError: If the API returns a non-2xx response or the
                requested date is missing from the payload.
        """
        ...


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class WeatherApiError(Exception):
    """Raised when the weather API returns an error or malformed response."""

    def __init__(self, status_code: int, description: str) -> None:
        self.status_code = status_code
        self.description = description
        super().__init__(f"Weather API error {status_code}: {description}")


# ---------------------------------------------------------------------------
# Production implementation
# ---------------------------------------------------------------------------


class HttpWeatherClient:
    """Fetches daily forecasts from Open-Meteo via HTTPS.

    Uses ``urllib`` from the standard library to avoid adding an HTTP client
    dependency to the Lambda package.

    Args:
        latitude:  Location latitude in decimal degrees.
        longitude: Location longitude in decimal degrees.
    """

    def __init__(self, latitude: float, longitude: float) -> None:
        self._latitude = latitude
        self._longitude = longitude

    # ------------------------------------------------------------------
    # WeatherClientProtocol implementation
    # ------------------------------------------------------------------

    def get_forecast(self, target_date: date) -> DailyForecast:
        """GET the daily forecast for ``target_date`` and parse it.

        Args:
            target_date: The calendar date to forecast.

        Returns:
            A populated ``DailyForecast``.

        Raises:
            WeatherApiError: On a non-2xx response or malformed/missing data.
        """
        iso_date = target_date.isoformat()
        query = urllib.parse.urlencode(
            {
                "latitude": self._latitude,
                "longitude": self._longitude,
                "daily": _DAILY_VARS,
                "timezone": "UTC",
                "start_date": iso_date,
                "end_date": iso_date,
            }
        )
        url = f"{_OPEN_METEO_BASE}/v1/forecast?{query}"

        logger.debug(
            "Fetching weather forecast",
            extra={"date": iso_date, "lat": self._latitude, "lon": self._longitude},
        )

        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req) as resp:  # noqa: S310 (url built from our config)
                body: dict[str, Any] = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                parsed = json.loads(raw)
                description = parsed.get("reason", str(exc))
            except (json.JSONDecodeError, AttributeError):
                description = raw.decode(errors="replace")
            raise WeatherApiError(exc.code, description) from exc

        forecast = self._parse_daily(body, target_date)
        logger.info("Fetched weather forecast", extra={"date": iso_date})
        return forecast

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_daily(body: dict[str, Any], target_date: date) -> DailyForecast:
        """Extract the single-day forecast from the parallel ``daily`` arrays.

        Args:
            body:        The decoded JSON response.
            target_date: The date that was requested (used to locate the index).

        Returns:
            A populated ``DailyForecast``.

        Raises:
            WeatherApiError: If ``daily`` is missing, malformed, or does not
                contain the requested date.
        """
        daily = body.get("daily")
        if not isinstance(daily, dict):
            raise WeatherApiError(0, "malformed response: 'daily' missing or not an object")

        times = daily.get("time")
        if not isinstance(times, list) or target_date.isoformat() not in times:
            raise WeatherApiError(0, f"forecast for {target_date.isoformat()} not in response")

        index = times.index(target_date.isoformat())
        try:
            return DailyForecast(
                forecast_date=target_date,
                temperature_max=float(daily["temperature_2m_max"][index]),
                uv_index=float(daily["uv_index_max"][index]),
                rain_probability=int(daily["precipitation_probability_max"][index]),
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise WeatherApiError(0, f"malformed daily data: {daily!r}") from exc


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_weather_client() -> HttpWeatherClient:
    """Return a cached ``HttpWeatherClient`` wired from application settings.

    Called once per Lambda container lifetime.
    Call ``get_weather_client.cache_clear()`` in tests to reset.
    """
    from hrse.config import get_settings

    settings = get_settings()
    return HttpWeatherClient(
        latitude=settings.weather_latitude,
        longitude=settings.weather_longitude,
    )
