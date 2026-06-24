# HRSE — Architecture

> Status: **Sprint 4 Complete**
> Last updated: 2026-06-24

---

## 1. Overview

The **Household Resource Scheduling Engine (HRSE)** is a serverless, event-driven system that recommends optimal times to run household tasks (starting with laundry) based on electricity price, weather forecasts, and weekly activity tracking.

It runs entirely on AWS managed services with zero operational overhead. Users interact via a Telegram bot. The system recommends — it does not control appliances.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AWS (eu-west-2)                             │
│                                                                     │
│   EventBridge (cron)                                                │
│   ┌─────────────────────────────────────────────────┐              │
│   │  16:45 UTC → DailyPlanning                      │              │
│   │  08:00 UTC → MorningReminder                    │              │
│   └───────────────────┬─────────────────────────────┘              │
│                       │                                             │
│            ┌──────────▼──────────┐                                 │
│            │  schedule-handler   │◄── Octopus Agile API            │
│            │  (Lambda)           │◄── Open-Meteo API               │
│            │                     │◄── S3 event store               │
│            │  DecisionService    │                                 │
│            │  (5 rules)          │                                 │
│            └──────────┬──────────┘                                 │
│                       │ send_message                                │
│                       ▼                                             │
│            ┌──────────────────────┐                                │
│            │  Telegram Bot API    │──────────────► You             │
│            └──────────────────────┘                                │
│                                                                     │
│   API Gateway (POST /webhook)                                       │
│   ┌─────────────────────────────┐                                  │
│   │  telegram-handler (Lambda)  │◄── Telegram webhook              │
│   │  /health /laundry_done      │                                  │
│   │  /events  /summary          │──► S3 event store                │
│   └─────────────────────────────┘                                  │
│                                                                     │
│   S3: hrse-{env}-state/events/household_events.json                │
│   Secrets Manager: hrse/{env}/telegram (bot_token + chat_id)       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Inventory

| Component | Technology | Purpose |
|---|---|---|
| `schedule-handler` | AWS Lambda (Python 3.12) | Fetches prices + weather, runs engine, sends notifications |
| `telegram-handler` | AWS Lambda (Python 3.12) | Receives webhook commands, writes events, sends replies |
| EventBridge rules | Amazon EventBridge | Two cron schedules: 16:45 (planning) and 08:00 (reminder) |
| API Gateway HTTP API | Amazon API Gateway v2 | Exposes `POST /webhook` to Telegram |
| Event store | Amazon S3 | Household activity events as a JSON array |
| Secrets | AWS Secrets Manager | `bot_token` + `chat_id` for Telegram |
| Observability | Lambda Powertools + CloudWatch | Structured logging, X-Ray tracing |
| Infrastructure | Terraform | All resources versioned as code |

---

## 4. The Decision Engine

The `DecisionService` is a **pure Python service** — no AWS dependencies, fully unit-testable with in-memory stubs.

### Inputs

| Input | Source | Shape |
|---|---|---|
| `WeeklySummary` | S3 event store via `WeeklyStateService` | `laundry_count`, `total_events` |
| `list[PricePoint]` | Octopus Agile API | `timestamp` (UTC), `price_pence` per 30-min slot |
| `DailyForecast` | Open-Meteo API | `uv_index`, `rain_probability`, `temperature_max` |
| `LaundryTaskConfig` | Hardcoded defaults (config-driven in future) | Thresholds + constraints |

### Five Rules (evaluated in order)

```
Rule 1 — Target check
  laundry_count >= target_runs_per_week → NOT RECOMMENDED ("target met")

Rule 2 — Weather gate (day-level)
  uv_index <= min_uv            → NOT RECOMMENDED ("UV too low")
  rain_probability >= max_rain  → NOT RECOMMENDED ("rain too high")

Rule 3 — Valid windows
  Build all runs of duration_slots consecutive 30-min slots
  inside earliest_start..latest_finish
  None found → NOT RECOMMENDED ("no valid window")

Rule 4 — Price filter
  Keep windows where every slot is strictly below max_price
  None left → NOT RECOMMENDED ("no window below threshold")

Rule 5 — Rank
  Sort by total window cost (cheapest first)
  Tie-break: earliest start
  Return best candidate as RECOMMENDED
```

### Output

```python
Recommendation(
    task="laundry",
    recommended=True,
    window=RecommendationWindow(start=..., end=...),
    expected_price_pence=7.05,   # average p/kWh across the window
    reasons=["laundry target not met", "electricity below threshold", ...]
)
```

---

## 5. Data Flows

### 5.1 Daily Planning (16:45 UTC)

```
EventBridge → schedule-handler Lambda
    │
    ├─► OctopusAgileClient.get_prices(tomorrow 00:00 → 00:00)
    │       Octopus REST API → list[PricePoint]
    │
    ├─► WeatherClient.get_forecast(tomorrow)
    │       Open-Meteo API → DailyForecast
    │
    ├─► S3EventStore.list_events()
    │       WeeklyStateService.get_summary() → WeeklySummary
    │
    ├─► DecisionService.evaluate(summary, prices, forecast, config)
    │       → Recommendation
    │
    └─► NotificationService.format(rec, PLANNING)
            HttpTelegramClient.send_message(chat_id, text)
                → Telegram → You
```

### 5.2 Morning Reminder (08:00 UTC)

Same flow as 5.1, but `target_date = today` and `kind = REMINDER`. Agile prices may have repriced overnight so the recommendation is re-evaluated fresh.

### 5.3 /laundry_done command

```
You → Telegram → API Gateway → telegram-handler Lambda
    │
    ├─► Event(event_type="laundry_completed", timestamp=utcnow())
    ├─► S3EventStore.append_event(event)
    ├─► WeeklyStateService.get_summary() → count this week
    └─► HttpTelegramClient.send_message("✅ Laundry recorded! X runs this week.")
```

---

## 6. External APIs

### Octopus Agile

| Property | Value |
|---|---|
| Base URL | `https://api.octopus.energy` |
| Endpoint | `/v1/products/{product}/electricity-tariffs/{tariff}/standard-unit-rates/` |
| Auth | None (public endpoint) |
| Resolution | 30-minute settlement periods |
| Price field | `value_inc_vat` (pence/kWh inc. VAT) |
| Publish time | ~16:00 UK time for next day |

### Open-Meteo

| Property | Value |
|---|---|
| Base URL | `https://api.open-meteo.com` |
| Endpoint | `/v1/forecast` |
| Auth | None (free, non-commercial) |
| Rate limit | 10,000 calls/day |
| Variables | `temperature_2m_max`, `uv_index_max`, `precipitation_probability_max` |

---

## 7. Storage Layout

```
s3://hrse-{environment}-state/
└── events/
    └── household_events.json    # JSON array, oldest-first, append-only
```

Example:
```json
[
  {"event_type": "laundry_completed", "timestamp": "2026-06-23T14:30:00.000Z"},
  {"event_type": "laundry_completed", "timestamp": "2026-06-25T09:15:00.000Z"}
]
```

**Week definition:** Monday 00:00:00 UTC (inclusive) → Sunday 23:59:59 UTC (inclusive), per ISO 8601.

---

## 8. Security

| Concern | Approach |
|---|---|
| Bot token + chat ID | Stored in Secrets Manager; fetched at cold-start, cached in-process |
| Lambda IAM roles | Least-privilege; scoped to specific S3 prefix and one secret ARN |
| S3 bucket | Versioning enabled, AES256 encryption, all public access blocked |
| Webhook payload logging | `log_event=False` on telegram-handler to avoid logging user messages |
| Environment variables | No secrets in env vars or Terraform state |

Schedule Lambda IAM grants:
- `secretsmanager:GetSecretValue` on `hrse/{env}/telegram`
- `s3:GetObject`, `s3:PutObject` on `hrse-{env}-state/events/*`
- `s3:ListBucket` on `hrse-{env}-state`

---

## 9. Observability

- Structured JSON logging via Lambda Powertools (`Logger`), `child=True` for module loggers.
- AWS X-Ray tracing via `@tracer.capture_lambda_handler` on both handlers.
- CloudWatch log groups with 30-day retention, managed by Terraform.

---

## 10. Key Design Decisions

| Decision | Rationale |
|---|---|
| `Protocol` not ABC for all clients | Structural typing — stubs need no inheritance; test doubles are plain classes |
| Pure services (no AWS deps) | `DecisionService`, `WeeklyStateService`, `NotificationService` are fully unit-testable with constructed inputs |
| S3 JSON array over DynamoDB | Sufficient for single-household v1 volume; zero table management; human-readable |
| `urllib` over `httpx`/`requests` | No extra Lambda package weight; both APIs are simple GET/POST |
| `lru_cache` factories | Single client instance per Lambda container lifetime; easily cleared in tests |
| EventBridge `detail-type` routing | One Lambda, two behaviours — avoids deploying a second function for the reminder |
| `from __future__ import annotations` | Defers annotation evaluation; enables `TYPE_CHECKING` imports for zero-cost runtime typing |

---

## 11. Known Limitations

| Issue | Impact | Planned fix |
|---|---|---|
| S3 read-modify-write with no concurrency control | Concurrent Lambda invocations could lose events | S3 conditional puts (ETag) or move events to DynamoDB |
| `LaundryTaskConfig` hardcoded in handler | Config changes require a redeploy | Make config-driven via S3 or env vars |
| Single household per deployment | No multi-tenant support | Future: household ID in event key prefix |
| UTC-only week definition | Households in other timezones see slightly wrong week boundaries | Add `HRSE_TIMEZONE` config |

---

## 12. Future Extensibility

The plugin architecture (Section 15 of requirements) is scaffolded but not yet implemented. Future tasks will follow the same Protocol + pure-service pattern:

```python
# Each task will implement:
class FlexibleTask(Protocol):
    def evaluate(self, ...) -> Recommendation: ...
    def config(self) -> TaskConfig: ...
```

Candidates: `DishwasherTask`, `EVChargingTask`, `CoolingTask`.
