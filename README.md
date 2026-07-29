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
| Sprint 6 | Group onboarding (bilingual EN/中文 welcome + language setting) + `/prices` chart | ✅ Done |
| Timezone fix | Notification display timezone is configurable, correct across the GMT/BST boundary | ✅ Done |
| Sprint 5A | Laundry thresholds moved from hardcoded Python to env-driven `Settings` | ✅ Done |
| Sprint 5B | Per-chat `/setup` onboarding, `TaskProfile`, `/profile`, `/reset` | ✅ Done |
| Sprint 5C | Generic `FlexibleTaskConfig`, task registry, `/tasks` `/add_task` `/remove_task` | ✅ Done |

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

`DecisionService.evaluate()` takes any `FlexibleTaskConfig` (laundry, dishwasher, EV charging, ...) — see [Multi-task support](#multi-task-support) below. One known gap: Rule 1's weekly count is currently always `laundry_count`, since per-task activity tracking doesn't exist yet — every task type's target check is gated by the same laundry counter until that's generalised.

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
docker compose build --no-cache lambda-builder 2>&1
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
| `/start` | Bilingual welcome + language picker |
| `/language` | Change the chat's language (English / 中文) |
| `/prices` | Today's Agile prices — cheapest-window bar chart |
| `/prices_tomorrow` | Tomorrow's prices (published ~16:00 UK time) |
| `/setup` | Configure this chat's own laundry preferences (6-question conversation) |
| `/profile` | Show this chat's current settings, or a hint to run `/setup` |
| `/reset` | Clear this chat's settings — revert to the global defaults |
| `/tasks` | List which tasks (laundry, dishwasher, ev) this chat gets recommendations for |
| `/add_task <name>` | Enable a task (`laundry`, `dishwasher`, or `ev`) |
| `/remove_task <name>` | Disable a task |
| `/health` | Service status check |
| `/laundry_done` | Record a completed laundry run |
| `/events` | Last 10 events with timestamps |
| `/summary` | This week's laundry count |

### Group onboarding & language

When the bot is added to a group (`my_chat_member` update — delivered even
with privacy mode on), it sends a bilingual welcome with an inline keyboard.
The chosen language is stored per chat in S3 (`settings/{chat_id}.json`) and
applied to all command replies. Commands in groups arrive as
`/command@BotName`; the suffix is stripped automatically.

Day boundaries and displayed times for `/prices` use, in order of
preference: the chat's own `TaskProfile.timezone` (set during `/setup`),
then `HRSE_DISPLAY_TIMEZONE` (IANA name, default `Europe/London` — correct
across GMT/BST). Scheduled notifications follow the same precedence.

### Configuration: global defaults vs per-chat profile

Every laundry threshold has three possible sources, resolved in this order
by `LaundryTaskConfig.from_profile_or_settings()`:

1. **Per-chat profile** — set via `/setup`, stored as `ChatSettings.profile`
   (a `TaskProfile`). Wins whenever present.
2. **Global `Settings`** (env vars, see below) — used by any chat that
   hasn't run `/setup`.
3. **Field defaults** baked into `LaundryTaskConfig` itself — the final
   fallback if neither of the above is set.

A chat's `/setup` answers cover 6 of the constraints (laundry target,
earliest/latest time, outdoor drying, timezone, wash budget); the rest
(`duration_slots`, `machine_kwh`, `min_uv`, `max_rain_probability`) always
come from the global `Settings` defaults, even for a chat with a profile —
`/setup` intentionally stays short.

### Multi-task support

Beyond laundry, HRSE ships two more flexible-task types out of the box:

| Registry key | Config class | Notes |
|---|---|---|
| `laundry` | `LaundryTaskConfig` | The original task; supports per-chat profiles via `/setup` |
| `dishwasher` | `DishwasherConfig` | Shorter cycle, no weather gate (runs indoors) |
| `ev` | `EVChargingConfig` | Long overnight session, no weather gate |

Every chat's enabled tasks are tracked in `ChatSettings.enabled_tasks`
(default `["laundry"]`, so existing chats are unaffected). Manage them with
`/tasks`, `/add_task <name>`, `/remove_task <name>`. The scheduler runs
`DecisionService.evaluate()` once per enabled task and sends one Telegram
message with a block per task — a chat with only laundry enabled still gets
the original single-block message.

`dishwasher` and `ev` currently use their built-in defaults only; unlike
laundry there's no onboarding flow or env-driven config for them yet — see
`TASK_REGISTRY` in `src/hrse/models/task_config.py` if you want to add one.

### Daily notifications

The timezone label (`BST`/`GMT`/etc.) is derived dynamically from
`HRSE_DISPLAY_TIMEZONE` (or the chat's own profile timezone) at the
notification's instant, so it's correct year-round — not hardcoded.

**16:45 UTC — Tomorrow's Energy Plan** (single task enabled — the default)
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

**08:00 UTC — Morning Reminder**
```
⏰ Morning Reminder

👕 Time to run laundry!
🕐 Window: 13:00–15:00 BST  (12:00–14:00 UTC)
⚡ Estimated wash cost: 22.0p

Reply /laundry_done when finished.
```

With more than one task enabled (`/add_task dishwasher`), the message
gains one block per task instead:
```
🏠 Tomorrow's Energy Plan

🧺 Laundry
✅ Recommended
🕐 Best window: 13:00–15:00 BST  (12:00–14:00 UTC)
⚡ Estimated cost: 22.0p
  ✓ laundry target not met

🍽 Dishwasher
❌ Not recommended
  • laundry target already met
```

---

## Environment Variables

All variables use the `HRSE_` prefix. Copy `.env.example` to `.env` for local development.

| Variable | Default | Description |
|---|---|---|
| `HRSE_AWS_REGION` | `eu-west-2` | AWS region |
| `HRSE_LOG_LEVEL` | `INFO` | Lambda log level (`DEBUG`\|`INFO`\|`WARNING`\|`ERROR`) |
| `HRSE_STATE_BUCKET_NAME` | `hrse-dev-state` | S3 bucket for event storage |
| `HRSE_TELEGRAM_SECRET_NAME` | `hrse/dev/telegram` | Secrets Manager secret (bot_token + chat_id) |
| `HRSE_OCTOPUS_PRODUCT_CODE` | `AGILE-24-10-01` | Octopus Agile product code |
| `HRSE_OCTOPUS_TARIFF_CODE` | `E-1R-AGILE-24-10-01-A` | Regional tariff code — change trailing letter for your region |
| `HRSE_WEATHER_LATITUDE` | `51.5072` | Forecast latitude (default: London) |
| `HRSE_WEATHER_LONGITUDE` | `-0.1276` | Forecast longitude (default: London) |
| `HRSE_DISPLAY_TIMEZONE` | `Europe/London` | IANA timezone for `/prices` day boundaries + notification labels (GMT/BST-correct) |
| `HRSE_DURATION_SLOTS` | `4` | Cheapest-window length `/prices` highlights, in 30-min slots (4 = 2h) |
| `HRSE_LAUNDRY_TARGET_PER_WEEK` | `2` | Global default: desired laundry runs per week (Sprint 5A) |
| `HRSE_EARLIEST_START` | `08:00` | Global default: earliest allowed start time, `HH:MM` |
| `HRSE_LATEST_FINISH` | `22:00` | Global default: latest allowed finish time, `HH:MM` |
| `HRSE_WASH_BUDGET_PENCE` | `40.0` | Global default: max spend per wash in pence |
| `HRSE_MACHINE_KWH` | `1.5` | Global default: energy per wash cycle in kWh |
| `HRSE_MIN_UV` | `3.0` | Global default: minimum UV index to recommend laundry |
| `HRSE_MAX_RAIN_PROBABILITY` | `40` | Global default: maximum rain probability (%) to recommend laundry |
| `HRSE_ENABLE_OPTIMISER` | `false` | Feature flag (reserved) |

The seven `HRSE_LAUNDRY_TARGET_PER_WEEK`…`HRSE_MAX_RAIN_PROBABILITY` variables
are the **global** defaults from Sprint 5A — any chat that hasn't run
`/setup` uses these. A chat with its own `TaskProfile` overrides them; see
[Configuration](#configuration-global-defaults-vs-per-chat-profile) above.

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
│   │   ├── schedule_handler.py   # EventBridge → fetch → decide → notify (per enabled task)
│   │   └── telegram_handler.py   # Webhook → command router
│   ├── models/
│   │   ├── chat_settings.py      # ChatSettings, TaskProfile, onboarding_step, enabled_tasks
│   │   ├── task_config.py        # FlexibleTaskConfig Protocol, Laundry/Dishwasher/EV configs, TASK_REGISTRY
│   │   └── ...                   # pricing, weather, recommendation
│   ├── services/
│   │   ├── decision_engine.py    # Five-rule engine, generic over FlexibleTaskConfig (100% coverage)
│   │   ├── notification.py       # Telegram formatter — format() single-task, format_multi() per-task blocks
│   │   └── weekly_state.py       # Weekly event aggregation
│   ├── store/              # S3 event + chat-settings stores + Protocols
│   ├── telegram/           # Bot client, commands (incl. /setup, /tasks), router, token/chat_id providers
│   └── utils/datetime_utils.py   # utcnow, to_iso8601, parse_hhmm (shared HH:MM parsing)
├── tests/unit/             # 400+ tests, 95%+ coverage
├── infra/                  # Terraform (Lambda, EventBridge, S3, API Gateway, IAM)
├── demo.py                 # Local end-to-end test (--mock or live)
├── mock_server.py          # Local mock for Octopus + Open-Meteo APIs
└── docs/
    ├── architecture.md
    ├── roadmap.md
    └── requirements.md
```

---

## Known Limitations

| Issue | Impact | Plan |
|---|---|---|
| ~~BST hardcoded in notifications~~ | ~~Broke in winter (Oct–Mar) when UK is GMT~~ | ✅ Resolved — `NotificationService(display_tz=...)`, label derived from `tzname()` |
| ~~`LaundryTaskConfig` hardcoded in handler~~ | ~~Config changes required a redeploy~~ | ✅ Resolved — env-driven `Settings` (5A) + per-chat `TaskProfile` (5B) |
| Rule 1 (target check) uses `laundry_count` for every task type | A dishwasher/EV target check is gated by the laundry counter, not its own | Generalise `WeeklySummary`/events to per-task counts |
| `dishwasher`/`ev` have no onboarding or env config | Only their hardcoded `TASK_REGISTRY` defaults are used | Extend `/setup` or add per-task env vars |
| S3 read-modify-write, no concurrency control | Could lose events if two Lambdas write simultaneously | Low risk now; fix before scaling |
| Single household per deployment | No multi-tenant support | Future architecture sprint |
| UTC-only week definition | Households far from UTC see slightly wrong week boundaries | Use `HRSE_DISPLAY_TIMEZONE` in `WeeklyStateService` |

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
