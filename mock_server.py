#!/usr/bin/env python3
"""mock_server.py — Local mock for Octopus Agile + Open-Meteo APIs.

Starts an HTTP server on localhost:8080 that returns realistic fake data.
Use this when you don't have real API access or want deterministic testing.

Usage:
    # Terminal 1 — start the mock server
    uv run python mock_server.py

    # Terminal 2 — run demo against the mock
    uv run python demo.py --mock

The mock generates a realistic Agile price profile:
  - Cheap overnight (00:00-06:00): 3-8p
  - Morning peak (06:00-09:00):   18-28p
  - Cheap midday (10:00-15:00):   6-12p
  - Evening peak (16:00-20:00):   20-35p
  - Cheap late (20:00-23:30):     8-14p
"""

from __future__ import annotations

import json
import math
import random
from datetime import UTC, date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

_PORT = 8080
_SLOT = timedelta(minutes=30)


# ---------------------------------------------------------------------------
# Price profile — mimics a realistic Agile day
# ---------------------------------------------------------------------------


def _agile_price(hour: float) -> float:
    """Return a realistic Agile price for a given hour of day (0-24)."""
    # Base sinusoidal with two peaks (morning + evening)
    morning_peak = 20 * math.exp(-((hour - 7.5) ** 2) / 4)
    evening_peak = 28 * math.exp(-((hour - 18) ** 2) / 5)
    base = 8 + morning_peak + evening_peak
    # Add a little noise so it looks real
    noise = random.uniform(-1.5, 1.5)
    return round(max(base + noise, -2.0), 2)  # Agile can go negative


def _generate_prices(target: date) -> list[dict[str, str | float]]:
    """Generate 48 half-hourly price slots for the target date."""
    results = []
    base = datetime(target.year, target.month, target.day, 0, 0, tzinfo=UTC)
    for i in range(48):
        slot_start = base + i * _SLOT
        slot_end = slot_start + _SLOT
        hour = slot_start.hour + slot_start.minute / 60
        price_inc = _agile_price(hour)
        price_exc = round(price_inc / 1.05, 2)  # approx ex-VAT
        results.append(
            {
                "value_exc_vat": price_exc,
                "value_inc_vat": price_inc,
                "valid_from": slot_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "valid_to": slot_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    return results


def _generate_weather(target: date) -> dict[str, object]:
    """Generate a realistic daily weather summary."""
    return {
        "latitude": 51.5072,
        "longitude": -0.1276,
        "timezone": "UTC",
        "daily_units": {
            "time": "iso8601",
            "temperature_2m_max": "°C",
            "uv_index_max": "",
            "precipitation_probability_max": "%",
        },
        "daily": {
            "time": [target.isoformat()],
            "temperature_2m_max": [round(random.uniform(15.0, 28.0), 1)],
            "uv_index_max": [round(random.uniform(3.0, 8.0), 1)],
            "precipitation_probability_max": [random.randint(5, 35)],
        },
    }


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        print(f"  [mock] {self.path.split('?')[0]}")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        # ------------------------------------------------------------------
        # Octopus Agile standard-unit-rates
        # Match: /v1/products/.../electricity-tariffs/.../standard-unit-rates/
        # ------------------------------------------------------------------
        if "standard-unit-rates" in path:
            period_from_str = qs.get("period_from", [""])[0]
            try:
                period_from = datetime.fromisoformat(period_from_str.replace("Z", "+00:00"))
                target = period_from.date()
            except ValueError:
                target = datetime.now(tz=UTC).date()

            prices = _generate_prices(target)
            body = json.dumps(
                {"count": len(prices), "next": None, "previous": None, "results": prices}
            ).encode()
            self._respond(200, body)

        # ------------------------------------------------------------------
        # Open-Meteo forecast
        # Match: /v1/forecast
        # ------------------------------------------------------------------
        elif path == "/v1/forecast":
            start_date_str = qs.get("start_date", [""])[0]
            try:
                target = date.fromisoformat(start_date_str)
            except ValueError:
                target = (datetime.now(tz=UTC) + timedelta(days=1)).date()

            weather = _generate_weather(target)
            self._respond(200, json.dumps(weather).encode())

        else:
            self._respond(404, b'{"error": "not found"}')

    def _respond(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    random.seed(42)  # remove for non-deterministic prices each run
    server = HTTPServer(("localhost", _PORT), MockHandler)
    print(f"Mock server running on http://localhost:{_PORT}")
    print("Handles:")
    print("  GET /v1/products/.../standard-unit-rates/  → Octopus Agile prices")
    print("  GET /v1/forecast                           → Open-Meteo weather")
    print("\nIn another terminal:")
    print("  uv run python demo.py --mock")
    print("\nCtrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
