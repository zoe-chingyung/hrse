# HRSE Roadmap

> Version: 2.1
> Status: Sprint 5 in progress
> Last updated: 2026-06-24

---

## Current State

| Capability | Status |
|---|---|
| Telegram bot (commands + push notifications) | ✅ Live |
| AWS serverless deployment (Lambda + EventBridge) | ✅ Live |
| Octopus Agile price integration | ✅ Live |
| Open-Meteo weather integration | ✅ Live |
| Weekly event memory (S3 event sourcing) | ✅ Live |
| Laundry recommendation engine (5 rules) | ✅ Live |
| Docker build pipeline | ✅ Live |
| Decision model (wash budget vs per-slot cap) | ✅ Live |
| BST display in notifications | ✅ Live (hardcoded, see Sprint 5A) |

---

## Guiding Principles

- **Recommend, not control.** HRSE never touches appliances.
- **Under £1/month to run.** Lambda free tier + zero-cost APIs.
- **Deployable by non-AWS experts.** One `terraform apply` to live.
- **Decision logic independent from infrastructure.** Pure services, no AWS imports in the engine.
- **Extensible by design.** Laundry is the first plugin, not the whole product.

---

## Vision

HRSE is not a laundry bot.

HRSE is a **Household Resource Scheduling Engine**. Laundry is simply the first plugin.

> "Help households schedule flexible resource consumption intelligently, using energy prices, weather conditions, and user-defined constraints."

---

## Sprint 5A — Open Source Hardening

**Priority: Critical**
**Status: Partially done**

### Done
- Docker build pipeline (`Dockerfile`, `Dockerfile.lambda`, `docker-compose.yml`)
- Pre-commit hooks (ruff, mypy, pytest, terraform fmt)
- Makefile with `docker-check` and `docker-deploy` targets
- Decision model updated to wash budget (human-readable pence)
- BST/UTC dual display in Telegram notifications

### Remaining

**Config cleanup — move all hardcoded thresholds to env vars**

Currently `_DEFAULT_CONFIG` in `schedule_handler.py` is hardcoded Python. Any threshold change requires a redeploy. Move to environment variables so operators can tune without touching code:

```
HRSE_LAUNDRY_TARGET=2
HRSE_WASH_BUDGET_PENCE=40
HRSE_MACHINE_KWH=1.5
HRSE_DURATION_SLOTS=4
HRSE_EARLIEST_START=08:00
HRSE_LATEST_FINISH=22:00
HRSE_MIN_UV=3.0
HRSE_MAX_RAIN_PROBABILITY=40
```

**Timezone — make configurable, not UK-specific**

Current BST hardcode breaks in winter (clocks go back in October) and is useless for anyone outside the UK. Replace with an IANA timezone string:

```
HRSE_TIMEZONE=Europe/London    # UK (handles BST↔GMT automatically)
HRSE_TIMEZONE=Europe/Berlin    # Germany (CET/CEST)
HRSE_TIMEZONE=America/New_York # US East
```

Internal calculations always remain UTC. Only the display layer converts using `zoneinfo.ZoneInfo(settings.timezone)`. This is a one-file change in `notification.py` once the config field exists.

**Success criteria:** A new user can fork, fill in `.env`, run `terraform apply`, and receive Telegram recommendations within 30 minutes.

---

## Sprint 5B — User Onboarding Engine

**Priority: Critical**
**Status: Planned**

### Problem

Every personal setting in HRSE is currently hardcoded for Zoe. `_DEFAULT_CONFIG` in `schedule_handler.py` has her laundry target, her budget, her wash hours. Anyone else running this gets Zoe's preferences.

### Solution: User Profile + Telegram Onboarding

Introduce a `UserProfile` domain model stored in S3 alongside events. On first interaction, the bot walks the user through a setup conversation and persists their answers.

**UserProfile fields:**
```
laundry_target_per_week    int
wash_budget_pence          float
machine_kwh                float
earliest_start             str (HH:MM)
latest_finish              str (HH:MM)
min_uv                     float
max_rain_probability       int
timezone                   str (IANA, e.g. "Europe/London")
outdoor_drying             bool
```

**Onboarding flow (Telegram):**
```
Hello 👋 Let's set up your household.

How many laundry runs per week do you aim for? (e.g. 2)
What's the earliest you'd run the washing machine? (e.g. 08:00)
Latest finish time? (e.g. 22:00)
Do you dry outdoors? (yes / no)
What's your timezone? (e.g. Europe/London)
Max budget per wash in pence? (default: 40p)
```

**New commands:**
```
/profile   — show current settings
/settings  — update individual settings
/reset     — clear profile and restart onboarding
```

**Architecture note:** `DecisionService.evaluate()` already accepts a `LaundryTaskConfig` — `UserProfile` just becomes the source of that config instead of the hardcoded default. No engine changes needed.

**Success criteria:** A non-technical user can configure HRSE entirely from Telegram, with no `.env` editing required for personal preferences.

---

## Sprint 5C — Multi-Task Scheduling (Plugin Architecture)

**Priority: High**
**Status: Designed, not implemented**

### The abstraction is already there

`LaundryTaskConfig`, `DecisionService`, `Recommendation` are all designed to be task-agnostic. The engine doesn't know it's scheduling laundry — it knows it's scheduling a flexible task with a duration, price budget, and weather constraints.

### Phase 1 — Generic TaskConfig

Extract `LaundryTaskConfig` into a base `FlexibleTaskConfig` Protocol:

```python
class FlexibleTaskConfig(Protocol):
    task_name: str
    duration_slots: int
    wash_budget_pence: float
    machine_kwh: float
    earliest_start: str
    latest_finish: str
    min_uv: float
    max_rain_probability: int
    weekly_target: int
```

Concrete implementations: `LaundryConfig`, `DishwasherConfig`, `EVChargingConfig`.

### Phase 2 — Task Registry

```python
TASK_REGISTRY = {
    "laundry":    LaundryConfig,
    "dishwasher": DishwasherConfig,
    "ev":         EVChargingConfig,
}
```

`schedule_handler.py` iterates the registry and produces one `Recommendation` per task.

### Phase 3 — Telegram UX for multiple tasks

```
/add_task       — register a new task type
/remove_task    — deregister a task
/tasks          — list all active tasks
```

**Note:** Phase 1 and 2 are pure Python changes to the engine layer. Phase 3 requires Telegram conversation state management (a non-trivial addition). Keep them as separate PRs.

**Initial plugins:** Laundry (already exists), Dishwasher, EV Charging.

---

## Sprint 6 — Constraint-Based Scheduling

**Priority: Medium**
**Status: Exploratory**

### Problem

Sprint 5C schedules each task independently. But households have a **total load constraint** — you can't run laundry (2kWh) + dishwasher (1.5kWh) + EV charger (7kWh) at the same time without tripping the breaker.

### Solution

Move from independent recommendations to a joint optimisation:

```
Household load limit: 8kW

Tasks:
  Laundry:    2kW × 2hrs
  Dishwasher: 1.5kW × 1.5hrs
  EV:         7kW × 4hrs

Engine output:
  Laundry:    13:00 – 15:00
  Dishwasher: 15:00 – 16:30
  EV:         00:30 – 04:30  (overnight cheap + no load conflict)
```

### Technology options

- Custom greedy scheduler (fits current pure-Python ethos, no new deps)
- Google OR-Tools (powerful, adds a heavy dependency)
- Linear programming via `scipy.optimize` (middle ground)

**Recommendation:** Start with the greedy scheduler. The problem is simple enough at household scale that a proper solver adds complexity without proportionate benefit — until there are 5+ tasks competing simultaneously.

---

## Sprint 7 — Home Energy Platform

**Priority: Exploratory**
**Status: Vision only**

### Home Assistant integration

Expose recommendations and task state via a REST API that Home Assistant can consume as a sensor. HRSE remains recommendation-only — Home Assistant handles any physical automation.

### Public API

```
GET  /recommendations        — current task recommendations
GET  /profile                — household profile
POST /events                 — record a task completion
GET  /prices?date=YYYY-MM-DD — price data for a day
```

### Mobile app

A lightweight companion app (Flutter or React Native) for households who prefer not to use Telegram. Shows the daily schedule, lets you log completions, and adjusts settings.

### Multi-household SaaS

If HRSE goes beyond personal use, a multi-tenant model where each household gets an isolated deployment or a shared backend with per-household data isolation.

---

## Technical Debt Backlog

### Must fix before October 2026

| Issue | Why urgent | Fix |
|---|---|---|
| BST hardcoded in `notification.py` | UK clocks go back last Sunday of October — notifications will show wrong times | `HRSE_TIMEZONE` config + `zoneinfo` |
| `_DEFAULT_CONFIG` hardcoded in handler | Anyone forking gets Zoe's settings | Sprint 5A config cleanup |

### Should fix soon

| Issue | Notes |
|---|---|
| S3 read-modify-write no concurrency control | Safe now (single-Lambda writes), risky at scale — use ETag conditional puts |
| No dead-letter queue on EventBridge rules | Silent failures if Lambda errors — add DLQ + CloudWatch alarm |
| `uv.lock` pinned to old package versions | Run `uv lock --upgrade` periodically |

### Low priority

| Issue | Notes |
|---|---|
| Single household per deployment | Fine for personal use; needs architecture work for SaaS |
| No metrics dashboard | CloudWatch covers the basics for now |
| Recommendation explainability | The `reasons` list in `Recommendation` is a start |

---

## Dependency on external providers

| Provider | Risk | Mitigation |
|---|---|---|
| Octopus Agile API | Tariff product codes change when Octopus launches new products | `HRSE_OCTOPUS_PRODUCT_CODE` + `HRSE_OCTOPUS_TARIFF_CODE` are config-driven |
| Open-Meteo | Free tier (10k calls/day), no SLA | One call/day per Lambda — well within limits; add fallback weather gate if API fails |
| Telegram Bot API | Webhook architecture means Telegram must reach API Gateway | Standard Telegram reliability; no known alternatives needed |
