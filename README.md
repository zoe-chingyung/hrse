# Household Resource Scheduling Engine (HRSE)

HRSE is a serverless scheduling engine that optimises the allocation of household resources (appliances, energy slots, tasks) across time windows. It runs on AWS Lambda and is driven by event-based triggers via Amazon EventBridge.

---

## Project Status

> **Sprint 1 – Repository Setup** (in progress)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12 |
| Package manager | [uv](https://docs.astral.sh/uv/) |
| Lint / format | [Ruff](https://docs.astral.sh/ruff/) |
| Type checking | [mypy](https://mypy-lang.org/) (strict) |
| Testing | pytest + moto |
| Infrastructure | Terraform (AWS) |
| Deployment target | AWS Lambda |
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
# uv creates .venv automatically
source .venv/bin/activate   # Linux / macOS
.venv\Scripts\activate      # Windows
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
│   └── hrse/               # Main package (src layout)
│       ├── __init__.py
│       ├── config.py       # Environment / settings
│       ├── models/         # Pydantic domain models
│       ├── handlers/       # Lambda handler entry points
│       ├── services/       # Business logic (Sprint 2+)
│       └── utils/          # Shared utilities
├── tests/
│   ├── unit/
│   └── integration/
├── infra/                  # Terraform root module
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── modules/
│       └── lambda/
├── docs/
│   ├── architecture.md
│   └── requirements.md
├── .github/
│   └── workflows/
│       └── ci.yml
├── pyproject.toml
├── .python-version
└── README.md
```

---

## Documentation

- [Architecture](docs/architecture.md)
- [Requirements](docs/requirements.md)

---

## Contributing

1. Create a feature branch from `main`.
2. Run `uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest` before pushing.
3. Open a pull request — CI must be green.

---

## License

MIT
