"""Unit tests for the Open-Meteo weather client.

The HTTP implementation is tested by mocking ``urllib.request.urlopen`` so no
real network call is made. A protocol-satisfying in-memory stub is also
provided for downstream tests (e.g. the decision engine).
"""

from __future__ import annotations

import io
import json
import urllib.error
from datetime import date
from typing import Any

import pytest

from hrse.clients.weather import (
    HttpWeatherClient,
    WeatherApiError,
    WeatherClientProtocol,
    get_weather_client,
)
from hrse.models.weather import DailyForecast

# ---------------------------------------------------------------------------
# In-memory stub — satisfies WeatherClientProtocol without any network
# ---------------------------------------------------------------------------


class StubWeatherClient:
    """Returns a fixed forecast regardless of the requested date."""

    def __init__(self, forecast: DailyForecast) -> None:
        self._forecast = forecast

    def get_forecast(self, target_date: date) -> DailyForecast:
        return self._forecast


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


def _client() -> HttpWeatherClient:
    return HttpWeatherClient(latitude=51.5072, longitude=-0.1276)


def _daily_payload(target: str = "2026-06-23") -> dict[str, Any]:
    return {
        "latitude": 51.5,
        "longitude": -0.1,
        "daily": {
            "time": [target],
            "temperature_2m_max": [27.0],
            "uv_index_max": [7.0],
            "precipitation_probability_max": [10],
        },
    }


# ---------------------------------------------------------------------------
# Stub tests
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestStubSatisfiesProtocol:
    def test_stub_is_protocol_instance(self) -> None:
        stub = StubWeatherClient(
            DailyForecast(
                forecast_date=date(2026, 6, 23),
                temperature_max=20.0,
                uv_index=5.0,
                rain_probability=10,
            )
        )
        assert isinstance(stub, WeatherClientProtocol)

    def test_stub_returns_supplied_forecast(self) -> None:
        forecast = DailyForecast(
            forecast_date=date(2026, 6, 23),
            temperature_max=20.0,
            uv_index=5.0,
            rain_probability=10,
        )
        stub = StubWeatherClient(forecast)
        assert stub.get_forecast(date(2026, 6, 23)) == forecast


# ---------------------------------------------------------------------------
# HTTP client tests (mocked urlopen)
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestHttpWeatherClientParsing:
    def test_parses_daily_into_forecast(self, mocker: Any) -> None:
        mocker.patch(
            "urllib.request.urlopen", return_value=_fake_response(_daily_payload("2026-06-23"))
        )
        forecast = _client().get_forecast(date(2026, 6, 23))
        assert forecast.temperature_max == 27.0
        assert forecast.uv_index == 7.0
        assert forecast.rain_probability == 10
        assert forecast.forecast_date == date(2026, 6, 23)

    def test_selects_correct_index_for_date(self, mocker: Any) -> None:
        """When multiple days are returned, the requested date's index is used."""
        payload = {
            "daily": {
                "time": ["2026-06-22", "2026-06-23"],
                "temperature_2m_max": [18.0, 27.0],
                "uv_index_max": [3.0, 7.0],
                "precipitation_probability_max": [80, 10],
            }
        }
        mocker.patch("urllib.request.urlopen", return_value=_fake_response(payload))
        forecast = _client().get_forecast(date(2026, 6, 23))
        assert forecast.uv_index == 7.0
        assert forecast.rain_probability == 10


@pytest.mark.unit()
class TestHttpWeatherClientRequest:
    def test_request_targets_correct_url_with_params(self, mocker: Any) -> None:
        fake_open = mocker.patch(
            "urllib.request.urlopen", return_value=_fake_response(_daily_payload())
        )
        _client().get_forecast(date(2026, 6, 23))

        request = fake_open.call_args.args[0]
        url = request.full_url
        assert url.startswith("https://api.open-meteo.com/v1/forecast?")
        assert "latitude=51.5072" in url
        assert "longitude=-0.1276" in url
        assert "start_date=2026-06-23" in url
        assert "end_date=2026-06-23" in url
        assert "uv_index_max" in url
        assert request.method == "GET"


@pytest.mark.unit()
class TestHttpWeatherClientErrors:
    def test_http_error_raises_weather_api_error(self, mocker: Any) -> None:
        err = urllib.error.HTTPError(
            url="http://x",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=io.BytesIO(b'{"error":true,"reason":"bad var"}'),
        )
        mocker.patch("urllib.request.urlopen", side_effect=err)
        with pytest.raises(WeatherApiError) as exc_info:
            _client().get_forecast(date(2026, 6, 23))
        assert exc_info.value.status_code == 400

    def test_missing_daily_raises(self, mocker: Any) -> None:
        mocker.patch("urllib.request.urlopen", return_value=_fake_response({"latitude": 51.5}))
        with pytest.raises(WeatherApiError):
            _client().get_forecast(date(2026, 6, 23))

    def test_date_not_in_response_raises(self, mocker: Any) -> None:
        mocker.patch(
            "urllib.request.urlopen", return_value=_fake_response(_daily_payload("2026-06-22"))
        )
        with pytest.raises(WeatherApiError):
            _client().get_forecast(date(2026, 6, 23))

    def test_malformed_daily_values_raise(self, mocker: Any) -> None:
        payload = {
            "daily": {
                "time": ["2026-06-23"],
                "temperature_2m_max": [27.0],
                # uv_index_max missing
                "precipitation_probability_max": [10],
            }
        }
        mocker.patch("urllib.request.urlopen", return_value=_fake_response(payload))
        with pytest.raises(WeatherApiError):
            _client().get_forecast(date(2026, 6, 23))


@pytest.mark.unit()
class TestFactory:
    def test_factory_returns_client_from_settings(self) -> None:
        get_weather_client.cache_clear()
        client = get_weather_client()
        assert isinstance(client, HttpWeatherClient)
        get_weather_client.cache_clear()
