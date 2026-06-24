# Household Resource Scheduling Engine (HRSE)

HRSE is a serverless scheduling engine that recommends **when** to run household tasks (starting with laundry) based on real-time electricity prices, weather forecasts, and weekly activity tracking. It runs on AWS Lambda, delivers recommendations to your phone via Telegram, and is deployed with Terraform.

The system recommends — it does not control appliances.

---

## Project Status

| Sprint | Scope | Status |
|---|---|---|
| Sprint 1 | Repository skeleton, CI, Terraform foundation | ✅ Done |
| Sprint 2A | Telegram bot — `/health` command via API Gateway | ✅ Done |
| Sprint 2B | Event memory layer — S3 event store, `/laundry_done`, `/events`, `/summary` | ✅ Done |
| Sprint 3 | Data clients (Octopus Agile, Open-Meteo) + decision engine | ✅ Done |
| Sprint 4 | EventBridge scheduled rules + daily Telegram notifications | ✅ Done |
| Sprint 5 | Docker build pipeline + decision tuning (wash budget model) | ✅ Done |

---

## How It Works

```
EventBridge (cron)
    │
    ├── 16:45 UTC → DailyPlanning   (recommend for tomorrow)
    └── 08:00 UTC → MorningReminder (confirm for today)
                │
                ├── Octopus Agile API  → half-hourly prices
                ├── Open-Meteo API     → daily weather forecast
                └── S3 event store     → weekly laundry count
                            │
                      DecisionService
                      (5 rules, pure Python)
                            │
                    NotificationService
                            │
                     Telegram → You 📱
```

### The five decision rules

1. **Target check** — weekly laundry count already met? Stop.
2. **Weather gate** — UV above `min_uv` and rain below `max_rain_probability`?
3. **Valid windows** — find all runs of `duration_slots` consecutive 30-min slots inside `earliest_start`–`latest_finish`.
4. **Budget filter** — keep windows where `avg_price × machine_kwh < wash_budget_pence`.
5. **Rank** — cheapest window first, ties broken by earliest start.

### Why avg price × machine_kwh, not per-slot threshold?

The original approach rejected any window where a single slot exceeded a fixed price cap — too strict for real Agile pricing. The current model calculates the **total estimated wash cost** (avg p/kWh × energy consumed in kWh) and compares it to a human-readable budget in pence. A window with one expensive slot surrounded by cheap ones can still be affordable overall. Default budget: 40p per wash, 1.5 kWh per cycle → threshold ≈ 26.7p/kWh average.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12 |
| Package manager | [uv](https://docs.astral.sh/uv/) |
| Lint / format | Ruff |
| Type checking | mypy (strict) |
| Testing | pytest + moto |
| State store | Amazon S3 (JSON event log) |
| Scheduler | Amazon EventBridge (cron rules) |
| Infrastructure | Terraform ≥ 1.8 (AWS, eu-west-2) |
| Bot interface | Telegram Bot API (webhook + push) |
| Price data | Octopus Energy REST API (Agile, no key required) |
| Weather data | Open-Meteo forecast API (no key required) |
| Build | Docker (dev image + Lambda builder) |
| CI | GitHub Actions |

---

## Docker Setup

Docker is the recommended way to build and test HRSE. It eliminates Python version conflicts, Windows wheel issues, and gives every contributor an identical environment.

### Two images

**`Dockerfile` (dev image)**
Used for running tests, linting, and mypy. Based on `python:3.12-slim`. Contains the full dev dependency stack (pytest, mypy, ruff, moto).

**`Dockerfile.lambda` (Lambda builder)**
Used to produce the Lambda deployment package. Based on the official AWS Lambda Python 3.12 runtime image (`public.ecr.aws/lambda/python:3.12`). This guarantees the correct Linux ABI and glibc version regardless of your host OS — the built package is always deployable to AWS Lambda even when built on Windows or macOS.

### Why two separate images?

The dev image needs dev tools (mypy, ruff, moto) which add ~200MB and have no place in a Lambda package. The Lambda builder image needs the exact Lambda runtime environment (Amazon Linux 2, glibc 2.26) to produce compatible native wheels — running `pip install` on `python:3.12-slim` would produce wheels that crash on Lambda. Keeping them separate means your test environment is lean and your Lambda package is correct.

### Build the images (first time only)

```bash
docker compose build
```

### Common commands

| Task | Command |
|---|---|
| Run tests | `docker compose run --rm test` |
| Lint | `docker compose run --rm lint` |
| Typecheck | `docker compose run --rm typecheck` |
| Full quality gate | `make docker-check` |
| Interactive shell | `docker compose run --rm dev` |
| Run demo (live APIs) | `docker compose run --rm demo` |
| Start mock server | `docker compose up mock-server` |
| **Build Lambda package** | `docker compose run --rm lambda-builder` |
| **Build + deploy** | `make docker-deploy ENV=dev` |

### Build and deploy workflow

```bash
# 1. Build the Lambda package (produces lambda_packages/hrse/)
mkdir -p lambda_packages/hrse
docker compose run --rm lambda-builder

# 2. Deploy — Terraform zips lambda_packages/hrse/ and uploads to Lambda
cd infra && terraform apply -var environment=dev
```

Terraform's `archive_file` data source re-zips the directory on every apply and only uploads when the content hash changes, so deploys are fast when only code changed.

---

## Local Development (without Docker)

```bash
# Install dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Lint and format
uv run ruff format . && uv run ruff check .

# Type check
uv run mypy
```

### Local end-to-end demo

```bash
cp .env.example .env   # fill in your values
uv run python demo.py --today       # recommend for today (live APIs)
uv run python demo.py               # recommend for tomorrow
```

Agile day-ahead prices publish around 16:00 UK time — run after that for tomorrow's recommendation.

### Mock server (no API keys needed)

```bash
# Terminal 1
uv run python mock_server.py

# Terminal 2
uv run python demo.py --mock --today
```

The mock server generates a realistic Agile price profile (cheap overnight, morning/evening peaks) and synthetic weather data on port 8080.

---

## Telegram Bot Setup

### 1. Create the secret in AWS Secrets Manager

Get your Telegram chat ID by messaging [@userinfobot](https://t.me/userinfobot).

```bash
aws secretsmanager create-secret \
  --region eu-west-2 \
  --name hrse/dev/telegram \
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

Send `/health` to your bot — you should receive:
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

**16:45 UTC (17:45 BST) — Tomorrow's Energy Plan**
```
🏠 Tomorrow's Energy Plan

✅ Laundry Recommended
🕐 Best window: 13:00–15:00 BST  (12:00–14:00 UTC)
⚡ Estimated wash cost: 22.0p

Reasons:
  ✓ laundry target not met
  ✓ wash cost within budget (40.0p)
  ✓ UV index above 3.0
  ✓ rain probability below 40%
```

**08:00 UTC (09:00 BST) — Morning Reminder**
```
⏰ Morning Reminder

👕 Time to run laundry!
🕐 Window: 13:00–15:00 BST  (12:00–14:00 UTC)
⚡ Estimated wash cost: 22.0p

Reply /laundry_done when finished.
```

---

## Environment Variables

All variables use the `HRSE_` prefix. Copy `.env.example` to `.env` for local development.

| Variable | Default | Description |
|---|---|---|
| `HRSE_AWS_REGION` | `eu-west-2` | AWS region |
| `HRSE_STATE_BUCKET_NAME` | `hrse-dev-state` | S3 bucket for event storage |
| `HRSE_TELEGRAM_SECRET_NAME` | `hrse/dev/telegram` | Secrets Manager secret (bot_token + chat_id) |
| `HRSE_OCTOPUS_PRODUCT_CODE` | `AGILE-FLEX-22-11-25` | Octopus Agile product code |
| `HRSE_OCTOPUS_TARIFF_CODE` | `E-1R-AGILE-FLEX-22-11-25-C` | Regional tariff code — change trailing letter for your region |
| `HRSE_WEATHER_LATITUDE` | `51.5072` | Forecast latitude (default: London) |
| `HRSE_WEATHER_LONGITUDE` | `-0.1276` | Forecast longitude (default: London) |
| `HRSE_ENABLE_OPTIMISER` | `false` | Feature flag (reserved) |

**Tariff region codes:** A=Eastern, B=East Midlands, C=London, D=Merseyside, E=Midlands, F=North East, G=North West, H=Southern, J=South East, K=South West, L=Yorkshire, M=South Scotland, N=North Scotland, P=North Wales.

---

## Project Layout

```
hrse/
├── Dockerfile              # Dev image (tests, lint, mypy)
├── Dockerfile.lambda       # Lambda builder (correct Linux wheels)
├── docker-compose.yml      # Orchestrates dev + build workflow
├── scripts/
│   └── build_lambda.sh     # Runs inside Lambda builder container
├── src/hrse/
│   ├── clients/
│   │   ├── octopus.py      # Octopus Agile price client
│   │   └── weather.py      # Open-Meteo weather client
│   ├── handlers/
│   │   ├── schedule_handler.py   # EventBridge → fetch → decide → notify
│   │   └── telegram_handler.py   # Webhook → command router
│   ├── models/             # Pydantic models (pricing, weather, task_config, recommendation)
│   ├── services/
│   │   ├── decision_engine.py    # Five-rule engine (pure Python, 100% coverage)
│   │   ├── notification.py       # Telegram message formatter (BST + UTC display)
│   │   └── weekly_state.py       # Weekly event aggregation
│   ├── store/              # S3 event store + Protocol
│   ├── telegram/           # Bot client, commands, router, token/chat_id providers
│   └── utils/datetime_utils.py
├── tests/unit/             # 181 tests, 98%+ coverage
├── infra/                  # Terraform (Lambda, EventBridge, S3, API Gateway, IAM)
├── demo.py                 # Local end-to-end test (--mock or live)
├── mock_server.py          # Local mock for Octopus + Open-Meteo APIs
└── docs/
    ├── architecture.md
    └── requirements.md
```

---

## Known Limitations

| Issue | Impact | Plan |
|---|---|---|
| BST hardcoded in notifications | Breaks in winter (Oct–Mar) when UK is GMT | Timezone sprint — user-configurable |
| `LaundryTaskConfig` hardcoded in handler | Config changes require redeploy | Onboarding sprint — Telegram prompts |
| S3 read-modify-write, no concurrency control | Could lose events if two Lambdas write simultaneously | Low risk now; fix before scaling |
| Single household per deployment | No multi-tenant support | Future architecture sprint |

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
