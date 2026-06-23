# Household Resource Scheduling Engine (HRSE)

HRSE is a serverless scheduling engine that helps a household decide **when** to run flexible tasks (starting with laundry) based on electricity price, weather, and how many runs are still needed this week. It runs on AWS Lambda, receives commands via a Telegram bot, persists state to S3, and is deployed with Terraform. The system provides recommendations — it does not control appliances.

---

## Project Status

| Sprint | Scope | Status |
|---|---|---|
| Sprint 1 | Repository skeleton, CI, Terraform foundation | ✅ Done |
| Sprint 2A | Telegram bot — `/health` command via API Gateway | ✅ Done |
| Sprint 2B | Event memory layer — S3 event store, `/laundry_done`, `/events`, `/summary` | ✅ Done |
| Sprint 3 | Data clients (Octopus Agile, Open-Meteo) + decision engine | 🔨 In progress |
| Sprint 4 | EventBridge handler wiring + daily recommendation notifications | 🔜 Planned |

**Sprint 3 detail:** the Octopus Agile price client, the Open-Meteo weather client, and the five-rule `DecisionService` are built and fully unit-tested. What remains is wiring them into the scheduled `schedule_handler` Lambda so a daily recommendation is generated and pushed to Telegram (Sprint 4).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12 |
| Package manager | [uv](https://docs.astral.sh/uv/) |
| Lint / format | [Ruff](https://docs.astral.sh/ruff/) |
| Type checking | [mypy](https://mypy-lang.org/) (strict) |
| Testing | pytest + moto |
| State store | Amazon S3 (JSON event log) |
| Infrastructure | Terraform ≥ 1.8 (AWS) |
| Deployment target | AWS Lambda (eu-west-2) |
| Bot interface | Telegram Bot API (webhook) |
| Price data | Octopus Energy REST API (Agile tariff) |
| Weather data | Open-Meteo forecast API |
| CI | GitHub Actions |

---

## How It Works

1. A scheduled Lambda (EventBridge) wakes up daily.
2. It fetches half-hourly electricity prices (Octopus Agile) and the day's weather forecast (Open-Meteo).
3. It loads the household's weekly activity from the S3 event store.
4. The `DecisionService` evaluates five rules and produces a recommendation.
5. The recommendation is delivered over Telegram.

Users record completed runs and query state through Telegram commands. Steps 1–4's building blocks exist today; the scheduled wiring in step 1/5 is Sprint 4.

### The decision rules

The `DecisionService` is a pure, dependency-free service that takes a weekly summary, a list of prices, a daily forecast, and a task config, and returns a `Recommendation`:

1. **Target check** — if the weekly laundry target is already met, stop.
2. **Weather gate** — require UV above `min_uv` and rain probability below `max_rain_probability`.
3. **Valid windows** — build candidate runs of `duration_slots` consecutive 30-minute slots inside the allowed `earliest_start`–`latest_finish` range.
4. **Price filter** — keep only windows where every slot is below `max_price`.
5. **Rank** — choose the cheapest window, breaking ties by earliest start.

---

## Getting Started

### Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Terraform ≥ 1.8](https://developer.hashicorp.com/terraform/install)
- AWS CLI configured with appropriate credentials

### Install dependencies

```bash
uv sync --extra dev
```

### Activate the virtual environment

```bash
source .venv/bin/activate   # Linux / macOS / Git Bash
.venv\Scripts\activate      # Windows cmd
```

### Run tests

```bash
uv run pytest
```

### Lint and format

```bash
uv run ruff check .
uv run ruff format .
```

### Type check

```bash
uv run mypy
```

---

## Project Layout

```
hrse/
├── src/
│   └── hrse/
│       ├── __init__.py
│       ├── config.py              # Pydantic Settings, HRSE_ env prefix
│       ├── handlers/
│       │   ├── schedule_handler.py   # EventBridge → Lambda (Sprint 4)
│       │   └── telegram_handler.py   # API Gateway → Lambda (Sprint 2A)
│       ├── clients/
│       │   ├── octopus.py            # OctopusClientProtocol + HttpOctopusClient
│       │   └── weather.py            # WeatherClientProtocol + HttpWeatherClient
│       ├── models/
│       │   ├── events.py             # Event, WeeklySummary
│       │   ├── pricing.py            # PricePoint
│       │   ├── recommendation.py     # Recommendation, RecommendationWindow
│       │   ├── task_config.py        # LaundryTaskConfig
│       │   ├── telegram.py           # TelegramUpdate, Message, Chat, User
│       │   └── weather.py            # DailyForecast
│       ├── services/
│       │   ├── decision_engine.py    # DecisionService — the five-rule engine
│       │   └── weekly_state.py       # WeeklyStateService — event aggregation
│       ├── store/
│       │   ├── protocol.py           # EventStore Protocol
│       │   └── s3_store.py           # S3EventStore + factory
│       ├── telegram/
│       │   ├── client.py             # TelegramClientProtocol + HttpTelegramClient
│       │   ├── commands.py           # handle_health, /laundry_done, /events, /summary
│       │   ├── router.py             # Command dispatcher
│       │   └── token_provider.py     # SecretsManagerTokenProvider
│       └── utils/
│           └── datetime_utils.py
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── clients/                  # Octopus + weather client tests
│   │   ├── telegram/                 # Sprint 2A/2B command + router tests
│   │   ├── test_config.py
│   │   ├── test_decision_engine.py   # DecisionService (100% coverage)
│   │   ├── test_decision_models.py   # pricing, weather, task_config, recommendation
│   │   ├── test_event_store.py
│   │   ├── test_weekly_state_service.py
│   │   └── test_schedule_handler.py
│   └── integration/
├── infra/
│   ├── main.tf                    # Lambda package + schedule_lambda
│   ├── telegram.tf                # telegram_lambda + API Gateway HTTP API
│   ├── state.tf                   # S3 state bucket
│   ├── variables.tf
│   ├── outputs.tf
│   └── modules/lambda/            # Reusable Lambda + IAM + log group module
├── docs/
│   ├── architecture.md
│   └── requirements.md
├── .github/workflows/ci.yml       # lint, typecheck, test, terraform validate
├── pyproject.toml
├── .python-version                # 3.12
└── Makefile
```

---

## Telegram Bot Setup

### 1. Create the secret in AWS Secrets Manager

```bash
aws secretsmanager create-secret \
  --region eu-west-2 \
  --name hrse/dev/telegram \
  --secret-string '{"bot_token":"<YOUR_BOT_TOKEN>"}'
```

### 2. Deploy infrastructure

```bash
cd infra
terraform init
terraform apply -var environment=dev
```

### 3. Register the webhook with Telegram

```bash
WEBHOOK_URL=$(terraform output -raw telegram_webhook_url)
BOT_TOKEN="<YOUR_BOT_TOKEN>"

curl -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -d "url=${WEBHOOK_URL}"
```

### 4. Test it

Send `/health` to your bot — you should receive:

```
✅ HRSE is healthy
Version: 0.1.0
```

### Available commands

| Command | Action |
|---|---|
| `/health` | Service status check |
| `/laundry_done` | Record a completed laundry run |
| `/events` | Show the 10 most recent events with timestamps |
| `/summary` | Weekly activity summary |

---

## Environment Variables

All variables use the `HRSE_` prefix.

| Variable | Default | Description |
|---|---|---|
| `HRSE_AWS_REGION` | `eu-west-2` | AWS region |
| `HRSE_STATE_BUCKET_NAME` | `hrse-dev-state` | S3 bucket for household event storage |
| `HRSE_LOG_LEVEL` | `INFO` | Lambda Powertools log level |
| `HRSE_TELEGRAM_SECRET_NAME` | `hrse/dev/telegram` | Secrets Manager secret name |
| `HRSE_OCTOPUS_PRODUCT_CODE` | `AGILE-FLEX-22-11-25` | Octopus Agile product code |
| `HRSE_OCTOPUS_TARIFF_CODE` | `E-1R-AGILE-FLEX-22-11-25-C` | Octopus regional tariff code |
| `HRSE_WEATHER_LATITUDE` | `51.5072` | Forecast latitude (default: London) |
| `HRSE_WEATHER_LONGITUDE` | `-0.1276` | Forecast longitude (default: London) |
| `HRSE_ENABLE_OPTIMISER` | `false` | Feature flag for the daily recommendation (Sprint 4) |

> **Tariff codes are regional.** The default tariff code ends in `-C`; change the trailing letter to match your grid supply point. See the Octopus product list for current codes.

Copy `.env.example` to `.env` for local development.

---

## Documentation

- [Architecture](docs/architecture.md)
- [Requirements](docs/requirements.md)

---

## Contributing

1. Branch from `main`.
2. Run the full check suite before pushing:
   ```bash
   uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest
   ```
3. Open a pull request — CI must be green before merging.

---

## License

MIT
