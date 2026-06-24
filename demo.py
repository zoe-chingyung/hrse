"""End-to-end demo: live (or mock) prices + weather -> decision engine.

Usage:
    uv run python demo.py              # real Octopus + Open-Meteo APIs
    uv run python demo.py --mock       # local mock server (port 8080)
    uv run python demo.py --mock --today  # use today instead of tomorrow

Start the mock server first if using --mock:
    uv run python mock_server.py
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

from hrse.clients.octopus import HttpOctopusClient, OctopusApiError
from hrse.clients.weather import HttpWeatherClient, WeatherApiError
from hrse.config import get_settings
from hrse.models.events import WeeklySummary
from hrse.models.task_config import LaundryTaskConfig
from hrse.services.decision_engine import DecisionService

# --- knobs you can play with -------------------------------------------------
FAKE_LAUNDRY_COUNT = 0  # bump to 2 to watch Rule 1 ("target met") trigger

CONFIG = LaundryTaskConfig(
    target_runs_per_week=2,
    duration_slots=4,  # 4 x 30min = 2-hour run
    earliest_start="08:00",
    latest_finish="22:00",
    max_price=15.0,
    min_uv=3.0,
    max_rain_probability=40,
)
# -----------------------------------------------------------------------------

_MOCK_PORT = 8080


def main() -> None:
    parser = argparse.ArgumentParser(description="HRSE end-to-end demo")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use local mock server instead of real APIs (run mock_server.py first)",
    )
    parser.add_argument(
        "--today",
        action="store_true",
        help="Recommend for today instead of tomorrow",
    )
    args = parser.parse_args()

    settings = get_settings()
    target_date = (
        datetime.now(tz=UTC).date()
        if args.today
        else (datetime.now(tz=UTC) + timedelta(days=1)).date()
    )

    # Override API base URLs when using mock server
    octopus_base = f"http://localhost:{_MOCK_PORT}" if args.mock else None
    weather_base = f"http://localhost:{_MOCK_PORT}" if args.mock else None

    print("=" * 60)
    print(f"HRSE demo — {'MOCK' if args.mock else 'LIVE'} — {target_date.isoformat()}")
    print("=" * 60)
    if args.mock:
        print(f"  Using mock server at http://localhost:{_MOCK_PORT}")
        print("  (start with: uv run python mock_server.py)\n")

    # Instantiate clients — pass override base URLs if mocking
    octopus_kwargs = {
        "product_code": settings.octopus_product_code,
        "tariff_code": settings.octopus_tariff_code,
    }
    weather_kwargs = {
        "latitude": settings.weather_latitude,
        "longitude": settings.weather_longitude,
    }

    if octopus_base:
        octopus = _PatchedOctopusClient(base=octopus_base, **octopus_kwargs)
    else:
        octopus = HttpOctopusClient(**octopus_kwargs)

    if weather_base:
        weather = _PatchedWeatherClient(base=weather_base, **weather_kwargs)
    else:
        weather = HttpWeatherClient(**weather_kwargs)

    # Fetch prices
    day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    try:
        prices = octopus.get_prices(day_start, day_end)
    except OctopusApiError as exc:
        print(f"\n[!] Could not fetch prices: {exc}")
        if not args.mock:
            print("    Try: uv run python demo.py --mock")
        return

    if not prices:
        print("\n[!] No prices returned — Agile prices publish ~4pm UK time.")
        print("    Try: uv run python demo.py --mock")
        return

    cheapest = min(prices, key=lambda p: p.price_pence)
    dearest = max(prices, key=lambda p: p.price_pence)
    print(f"\nPrices: {len(prices)} half-hour slots")
    print(f"  cheapest: {cheapest.price_pence:.2f}p at {cheapest.timestamp:%H:%M} UTC")
    print(f"  dearest:  {dearest.price_pence:.2f}p at {dearest.timestamp:%H:%M} UTC")

    # Fetch weather
    try:
        forecast = weather.get_forecast(target_date)
    except WeatherApiError as exc:
        print(f"\n[!] Could not fetch weather: {exc}")
        return

    print(
        f"\nWeather: {forecast.temperature_max:.0f}°C max, "
        f"UV {forecast.uv_index:.1f}, rain {forecast.rain_probability}%"
    )

    # Weekly summary (faked — real one lives in S3)
    summary = WeeklySummary(
        laundry_count=FAKE_LAUNDRY_COUNT,
        last_laundry_timestamp=None,
        total_events=FAKE_LAUNDRY_COUNT,
    )
    print(f"\nWeekly state: {summary.laundry_count}/{CONFIG.target_runs_per_week} runs done")

    # Run the engine
    rec = DecisionService().evaluate(
        summary=summary, prices=prices, forecast=forecast, config=CONFIG
    )

    # Print verdict
    print("\n" + "-" * 60)
    if rec.recommended and rec.window is not None:
        print("✅ RECOMMENDED: run laundry")
        print(f"   window: {rec.window.start:%H:%M} – {rec.window.end:%H:%M} UTC")
        print(f"   expected price: {rec.expected_price_pence}p/kWh")
        print("   reasons:")
        for r in rec.reasons:
            print(f"     ✓ {r}")
    else:
        print("❌ NOT recommended")
        print("   reasons:")
        for r in rec.reasons:
            print(f"     • {r}")
    print("-" * 60)


# ---------------------------------------------------------------------------
# Thin subclasses that override the API base URL for mock mode
# ---------------------------------------------------------------------------


class _PatchedOctopusClient(HttpOctopusClient):
    def __init__(self, base: str, **kwargs: str) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._base = base

    def get_prices(self, period_from: datetime, period_to: datetime):  # type: ignore[override]
        import json
        import urllib.parse
        import urllib.request

        from hrse.models.pricing import PricePoint
        from hrse.utils.datetime_utils import to_iso8601

        query = urllib.parse.urlencode(
            {
                "period_from": to_iso8601(period_from),
                "period_to": to_iso8601(period_to),
                "page_size": 1500,
            }
        )
        url = (
            f"{self._base}/v1/products/{self._product_code}"
            f"/electricity-tariffs/{self._tariff_code}/standard-unit-rates/?{query}"
        )
        with urllib.request.urlopen(url) as resp:  # noqa: S310
            body = json.loads(resp.read())
        points = [
            PricePoint(
                timestamp=datetime.fromisoformat(r["valid_from"]),
                price_pence=float(r["value_inc_vat"]),
            )
            for r in body["results"]
        ]
        return sorted(points, key=lambda p: p.timestamp)


class _PatchedWeatherClient(HttpWeatherClient):
    def __init__(self, base: str, **kwargs: float) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._base = base

    def get_forecast(self, target_date):  # type: ignore[override]
        import json
        import urllib.parse
        import urllib.request

        iso = target_date.isoformat()
        query = urllib.parse.urlencode(
            {
                "latitude": self._latitude,
                "longitude": self._longitude,
                "daily": "temperature_2m_max,uv_index_max,precipitation_probability_max",
                "timezone": "UTC",
                "start_date": iso,
                "end_date": iso,
            }
        )
        url = f"{self._base}/v1/forecast?{query}"
        with urllib.request.urlopen(url) as resp:  # noqa: S310
            body = json.loads(resp.read())
        return self._parse_daily(body, target_date)


if __name__ == "__main__":
    main()
