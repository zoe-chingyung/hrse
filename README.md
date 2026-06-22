# Household Resource Scheduling Engine (HRSE)

HRSE is a serverless scheduling engine that optimises the allocation of household resources (appliances, energy slots, tasks) across configurable time windows. It runs on AWS Lambda, receives commands via a Telegram bot, and is deployed with Terraform.

---

## Project Status

| Sprint | Scope | Status |
|---|---|---|
| Sprint 1 | Repository skeleton, CI, Terraform foundation | ✅ Done |
| Sprint 2A | Telegram bot — `/health` command via API Gateway | ✅ Done |
| Sprint 2B+ | Schedule management, DynamoDB, business logic | 🔜 Planned |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12 |
| Package manager | [uv](https://docs.astral.sh/uv/) |
| Lint / format | [Ruff](https://docs.astral.sh/ruff/) |
| Type checking | [mypy](https://mypy-lang.org/) (strict) |
| Testing | pytest + moto |
| Infrastructure | Terraform ≥ 1.8 (AWS) |
| Deployment target | AWS Lambda (eu-west-2) |
| Bot interface | Telegram Bot API (webhook) |
| CI | GitHub Actions |

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
│       │   ├── schedule_handler.py   # EventBridge → Lambda (Sprint 2B+)
│       │   └── telegram_handler.py   # API Gateway → Lambda (Sprint 2A)
│       ├── models/
│       │   ├── schedule.py           # Schedule, Resource, TimeWindow
│       │   └── telegram.py           # TelegramUpdate, Message, Chat, User
│       ├── telegram/
│       │   ├── client.py             # TelegramClientProtocol + HttpTelegramClient
│       │   ├── commands.py           # handle_health, handle_unknown
│       │   ├── router.py             # Command dispatcher
│       │   └── token_provider.py     # SecretsManagerTokenProvider
│       ├── services/                 # Business logic (Sprint 2B+)
│       └── utils/
│           └── datetime_utils.py
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── telegram/                 # ~60 test cases for Sprint 2A
│   │   ├── test_config.py
│   │   ├── test_models.py
│   │   └── test_schedule_handler.py
│   └── integration/
├── infra/
│   ├── main.tf                    # Lambda package + schedule_lambda
│   ├── telegram.tf                # telegram_lambda + API Gateway HTTP API
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

## Telegram Bot Setup (Sprint 2A)

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

---

## Environment Variables

All variables use the `HRSE_` prefix.

| Variable | Default | Description |
|---|---|---|
| `HRSE_AWS_REGION` | `eu-west-2` | AWS region |
| `HRSE_SCHEDULE_TABLE_NAME` | `hrse-schedules` | DynamoDB table name |
| `HRSE_LOG_LEVEL` | `INFO` | Lambda Powertools log level |
| `HRSE_TELEGRAM_SECRET_NAME` | `hrse/dev/telegram` | Secrets Manager secret name |
| `HRSE_ENABLE_OPTIMISER` | `false` | Feature flag for Sprint 3+ optimiser |

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
