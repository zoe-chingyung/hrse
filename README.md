# Household Resource Scheduling Engine (HRSE)

HRSE is a serverless scheduling engine that helps a household decide **when** to run flexible tasks (starting with laundry) based on electricity price, weather, and weekly activity tracking. It runs on AWS Lambda, delivers recommendations via Telegram, persists state to S3, and is deployed with Terraform.

The system provides recommendations — it does not control appliances.

---

## Project Status

| Sprint | Scope | Status |
|---|---|---|
| Sprint 1 | Repository skeleton, CI, Terraform foundation | ✅ Done |
| Sprint 2A | Telegram bot — `/health` command via API Gateway | ✅ Done |
| Sprint 2B | Event memory layer — S3 event store, `/laundry_done`, `/events`, `/summary` | ✅ Done |
| Sprint 3 | Data clients (Octopus Agile, Open-Meteo) + decision engine | ✅ Done |
| Sprint 4 | EventBridge scheduled rules + daily Telegram notifications | ✅ Done |

---

## How It Works

```
EventBridge (cron)
    │
    ▼
Schedule Lambda (16:45 → DailyPlanning / 08:00 → MorningReminder)
    │
    ├── Octopus Agile API  ──► PricePoint list
    ├── Open-Meteo API     ──► DailyForecast
    └── S3 Event Store     ──► WeeklySummary
                │
                ▼
          DecisionService (5 rules)
                │
                ▼
        NotificationService
                │
                ▼
         Telegram → You
```

Two EventBridge rules fire daily:

| Time (UTC) | Event | What it does |
|---|---|---|
| 16:45 | `DailyPlanning` | Fetches tomorrow's prices + weather, recommends a window |
| 08:00 | `MorningReminder` | Re-runs the engine for today (Agile prices may have repriced overnight) |

Users record completed runs and query state through Telegram commands.

### The five decision rules

The `DecisionService` is a pure, dependency-free service:

1. **Target check** — if the weekly laundry target is already met, stop.
2. **Weather gate** — require UV above `min_uv` and rain probability below `max_rain_probability`.
3. **Valid windows** — build candidate runs of `duration_slots` consecutive 30-minute slots inside `earliest_start`–`latest_finish`.
4. **Price filter** — keep only windows where every slot is below `max_price`.
5. **Rank** — cheapest window first, ties broken by earliest start.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12 |
| Package manager | [uv](https://docs.astral.sh/uv/) |
| Lint / format | [Ruff](https://docs.astral.sh/ruff/) |
| Type checking | mypy (strict) |
| Testing | pytest + moto |
| State store | Amazon S3 (JSON event log) |
| Scheduler | Amazon EventBridge (cron rules) |
| Infrastructure | Terraform ≥ 1.8 (AWS, eu-west-2) |
| Bot interface | Telegram Bot API (webhook) |
| Price data | Octopus Energy REST API (Agile tariff, no key required) |
| Weather data | Open-Meteo forecast API (no key required) |
| CI | GitHub Actions |

---

## Project Layout

```
hrse/
├── src/hrse/
│   ├── clients/
│   │   ├── octopus.py            # OctopusClientProtocol + HttpOctopusClient
│   │   └── weather.py            # WeatherClientProtocol + HttpWeatherClient
│   ├── handlers/
│   │   ├── schedule_handler.py   # EventBridge → fetch → decide → notify
│   │   └── telegram_handler.py   # API Gateway → Telegram command router
│   ├── models/
│   │   ├── events.py             # Event, WeeklySummary
│   │   ├── pricing.py            # PricePoint
│   │   ├── recommendation.py     # Recommendation, RecommendationWindow
│   │   ├── task_config.py        # LaundryTaskConfig
│   │   ├── telegram.py           # TelegramUpdate, Message, Chat
│   │   └── weather.py            # DailyForecast
│   ├── services/
│   │   ├── decision_engine.py    # DecisionService — five rules
│   │   ├── notification.py       # NotificationService — Telegram formatting
│   │   └── weekly_state.py       # WeeklyStateService — event aggregation
│   ├── store/
│   │   ├── protocol.py           # EventStore Protocol
│   │   └── s3_store.py           # S3EventStore + factory
│   ├── telegram/
│   │   ├── client.py             # TelegramClientProtocol + HttpTelegramClient
│   │   ├── commands.py           # /health, /laundry_done, /events, /summary
│   │   ├── router.py             # Command dispatcher
│   │   └── token_provider.py     # SecretsManagerTokenProvider + ChatIdProvider
│   └── utils/datetime_utils.py
├── tests/
│   ├── conftest.py
│   └── unit/
│       ├── clients/              # Octopus + weather client tests
│       ├── telegram/             # Command + router tests
│       ├── test_config.py
│       ├── test_decision_engine.py   # 100% coverage
│       ├── test_decision_models.py
│       ├── test_event_store.py
│       ├── test_notification.py
│       ├── test_schedule_handler.py  # end-to-end wired handler tests
│       └── test_weekly_state_service.py
├── infra/
│   ├── main.tf                   # Lambda package + schedule_lambda module
│   ├── schedule.tf               # EventBridge rules + IAM for schedule Lambda
│   ├── telegram.tf               # telegram_lambda + API Gateway HTTP API
│   ├── state.tf                  # S3 state bucket + IAM for telegram Lambda
│   ├── variables.tf
│   ├── outputs.tf
│   └── modules/lambda/           # Reusable Lambda + IAM + log group module
├── demo.py                       # Local end-to-end test (real APIs, no AWS)
├── .github/workflows/ci.yml
├── pyproject.toml
└── Makefile
```

---

## Getting Started

### Prerequisites

- Python 3.12, [uv](https://docs.astral.sh/uv/getting-started/installation/), [Terraform ≥ 1.8](https://developer.hashicorp.com/terraform/install), AWS CLI

### Install and run tests

```bash
uv sync --extra dev
uv run pytest
```

### Local end-to-end demo (real APIs, no AWS needed)

```bash
cp .env.example .env   # fill in your values
uv run python demo.py
```

This fetches live Octopus Agile prices and Open-Meteo weather and runs the decision engine. Agile day-ahead prices publish around 16:00 UK time, so run after that for tomorrow's recommendation.

---

## Telegram Bot Setup

### 1. Create the Telegram secret in Secrets Manager

The secret must contain both `bot_token` and `chat_id`. Get your chat ID by messaging [@userinfobot](https://t.me/userinfobot) on Telegram.

```bash
aws secretsmanager create-secret \
  --region eu-west-2 \
  --name hrse/dev/telegram \
  --secret-string '{"bot_token":"<YOUR_BOT_TOKEN>","chat_id":"<YOUR_CHAT_ID>"}'
```

To update an existing secret:
```bash
aws secretsmanager update-secret \
  --region eu-west-2 \
  --secret-id hrse/dev/telegram \
  --secret-string '{"bot_token":"<YOUR_BOT_TOKEN>","chat_id":"<YOUR_CHAT_ID>"}'
```

### 2. Deploy infrastructure

```bash
cd infra
terraform init
terraform apply -var environment=dev
```

### 3. Register the webhook

```bash
WEBHOOK_URL=$(terraform output -raw telegram_webhook_url)
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
  -d "url=${WEBHOOK_URL}"
```

### 4. Test it

Send `/health` to your bot — you should see:
```
✅ HRSE is healthy
Version: 0.1.0
```

### Telegram commands

| Command | Action |
|---|---|
| `/health` | Service status check |
| `/laundry_done` | Record a completed laundry run |
| `/events` | Last 10 events with timestamps |
| `/summary` | This week's laundry count |

### Daily notifications

Once deployed, the bot will message you automatically:

**16:45 UTC — Tomorrow's Energy Plan**
```
🏠 Tomorrow's Energy Plan

✅ Laundry Recommended
🕐 Best window: 13:00 – 15:00 UTC
⚡ Expected price: 7.05p/kWh

Reasons:
  ✓ laundry target not met
  ✓ electricity below threshold (15.0p/kWh)
  ✓ UV index above 3.0
  ✓ rain probability below 40%
```

**08:00 UTC — Morning Reminder**
```
⏰ Morning Reminder

👕 Time to run laundry!
🕐 Window: 13:00 – 15:00 UTC
⚡ Price: 7.05p/kWh

Reply /laundry_done when finished.
```

---

## Environment Variables

All variables use the `HRSE_` prefix. See `.env.example` for a complete template.

| Variable | Default | Description |
|---|---|---|
| `HRSE_AWS_REGION` | `eu-west-2` | AWS region |
| `HRSE_STATE_BUCKET_NAME` | `hrse-dev-state` | S3 bucket for household event storage |
| `HRSE_TELEGRAM_SECRET_NAME` | `hrse/dev/telegram` | Secrets Manager secret (bot_token + chat_id) |
| `HRSE_OCTOPUS_PRODUCT_CODE` | `AGILE-24-10-01` | Octopus Agile product code |
| `HRSE_OCTOPUS_TARIFF_CODE` | `E-1R-AGILE-24-10-01-A` | Octopus regional tariff code (change trailing letter for your region) |
| `HRSE_WEATHER_LATITUDE` | `51.5072` | Forecast latitude (default: London) |
| `HRSE_WEATHER_LONGITUDE` | `-0.1276` | Forecast longitude (default: London) |
| `HRSE_ENABLE_OPTIMISER` | `false` | Feature flag (reserved for future use) |

---

## Contributing

```bash
uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest
pre-commit run --all-files
```

CI must be green before merging.

---

## License

MIT
