"""End-to-end demo: live prices + live weather -> decision engine.

Run from the project root with:

    uv run python demo.py

This is a throwaway local script (not part of the package, not tested in CI).
It wires the *real* Octopus and Open-Meteo clients into the DecisionService
and prints a laundry recommendation for tomorrow — the same flow the Sprint 4
scheduled Lambda will eventually run, minus AWS and Telegram.

Notes
-----
* No AWS credentials needed: both APIs are public and key-free.
* The weekly summary is faked here (laundry_count=0) because the real one
  lives in S3. Change FAKE_LAUNDRY_COUNT below to see Rule 1 kick in.
* If Octopus returns no prices for tomorrow yet (Agile day-ahead prices
  publish ~4pm UK time), try again later or switch TARGET_DATE to today.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hrse.clients.octopus import HttpOctopusClient, OctopusApiError
from hrse.clients.weather import HttpWeatherClient, WeatherApiError
from hrse.config import get_settings
from hrse.models.events import WeeklySummary
from hrse.models.task_config import LaundryTaskConfig
from hrse.services.decision_engine import DecisionService

# --- knobs you can play with -------------------------------------------------
FAKE_LAUNDRY_COUNT = 0  # bump to 2 to watch Rule 1 ("target met") trigger
TARGET_DATE = (datetime.now(tz=UTC) + timedelta(days=1)).date()  # tomorrow

CONFIG = LaundryTaskConfig(
    target_runs_per_week=2,
    duration_slots=4,  # 4 x 30min = a 2-hour run
    earliest_start="08:00",
    latest_finish="22:00",
    max_price=15.0,
    min_uv=3.0,
    max_rain_probability=40,
)
# -----------------------------------------------------------------------------


def main() -> None:
    settings = get_settings()

    print("=" * 60)
    print(f"HRSE demo — recommendation for {TARGET_DATE.isoformat()}")
    print("=" * 60)

    # 1. Live electricity prices for the target day (00:00 -> next 00:00 UTC).
    octopus = HttpOctopusClient(
        product_code=settings.octopus_product_code,
        tariff_code=settings.octopus_tariff_code,
    )
    day_start = datetime(TARGET_DATE.year, TARGET_DATE.month, TARGET_DATE.day, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)

    try:
        prices = octopus.get_prices(day_start, day_end)
    except OctopusApiError as exc:
        print(f"\n[!] Could not fetch prices: {exc}")
        print("    Agile day-ahead prices publish ~4pm UK time; try later or use today.")
        return

    if not prices:
        print("\n[!] No prices returned for that day yet (likely not published).")
        print("    Try again after ~4pm UK, or set TARGET_DATE to today.")
        return

    cheapest = min(prices, key=lambda p: p.price_pence)
    dearest = max(prices, key=lambda p: p.price_pence)
    print(f"\nPrices: {len(prices)} half-hour slots")
    print(f"  cheapest: {cheapest.price_pence:.2f}p at {cheapest.timestamp:%H:%M}")
    print(f"  dearest:  {dearest.price_pence:.2f}p at {dearest.timestamp:%H:%M}")

    # 2. Live weather forecast for the target day.
    weather = HttpWeatherClient(
        latitude=settings.weather_latitude,
        longitude=settings.weather_longitude,
    )
    try:
        forecast = weather.get_forecast(TARGET_DATE)
    except WeatherApiError as exc:
        print(f"\n[!] Could not fetch weather: {exc}")
        return

    print(
        f"\nWeather: {forecast.temperature_max:.0f}C max, "
        f"UV {forecast.uv_index:.1f}, rain {forecast.rain_probability}%"
    )

    # 3. Weekly summary (faked — real one lives in S3).
    summary = WeeklySummary(
        laundry_count=FAKE_LAUNDRY_COUNT,
        last_laundry_timestamp=None,
        total_events=FAKE_LAUNDRY_COUNT,
    )
    print(
        f"\nWeekly state: {summary.laundry_count}/{CONFIG.target_runs_per_week} laundry runs done"
    )

    # 4. Run the engine.
    rec = DecisionService().evaluate(
        summary=summary, prices=prices, forecast=forecast, config=CONFIG
    )

    # 5. Print the verdict.
    print("\n" + "-" * 60)
    if rec.recommended and rec.window is not None:
        print("RECOMMENDED: run laundry")
        print(f"  window: {rec.window.start:%H:%M} - {rec.window.end:%H:%M} UTC")
        print(f"  expected price: {rec.expected_price_pence}p/kWh")
        print("  reasons:")
        for r in rec.reasons:
            print(f"    - {r}")
    else:
        print("NOT recommended")
        print("  reasons:")
        for r in rec.reasons:
            print(f"    - {r}")
    print("-" * 60)


if __name__ == "__main__":
    main()
