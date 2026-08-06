# HRSE — Requirements

> Status: **Sprint 4 Complete**
> Last updated: 2026-06-24

---

## 1. Vision

Create a lightweight scheduling engine that helps a household decide **when** to run flexible tasks based on electricity price, weather, and household state. The system provides recommendations — it does not control appliances.

---

## 2. Scope

The MVP supports one task type: **laundry**. The system determines whether laundry should be recommended, the best execution window, and the reasoning behind the recommendation.

### In scope (v1)
- Laundry task scheduling
- Octopus Agile electricity price integration
- Open-Meteo weather forecast integration
- S3 event sourcing for weekly activity tracking
- Telegram bot interface (commands + proactive notifications)
- AWS Lambda + EventBridge + Terraform deployment

### Out of scope (v1)
- Device control (SmartThings, Home Assistant, smart plugs)
- AI/LLM decision making
- Mobile applications (Telegram only)
- Real-time pricing streams

Multi-household registration (Sprint A, below) is in scope: any invited
chat can register itself as a notification recipient. What's still out of
scope is per-household *isolation* — every registered chat shares one
global region, task registry, and set of AWS resources; there's no
per-tenant config or data partitioning.

---

## 3. Functional Requirements

### 3.1 Scheduling

| ID | Requirement | Status |
|---|---|---|
| FR-01 | The engine SHALL evaluate whether a laundry run is recommended for a given day. | ✅ Done |
| FR-02 | The engine SHALL recommend a specific execution window (start + end time). | ✅ Done |
| FR-03 | The engine SHALL provide human-readable reasons for every verdict (recommended or not). | ✅ Done |
| FR-04 | The recommended window SHALL consist of `duration_slots` consecutive 30-minute price slots. | ✅ Done |
| FR-05 | The engine SHALL rank candidate windows by total cost, breaking ties by earliest start. | ✅ Done |

### 3.2 Decision Rules

| ID | Rule | Status |
|---|---|---|
| FR-10 | If the weekly laundry target is already met, do not recommend. | ✅ Done |
| FR-11 | Only recommend when the day's UV index is strictly above `min_uv`. | ✅ Done |
| FR-12 | Only recommend when the day's rain probability is strictly below `max_rain_probability`. | ✅ Done |
| FR-13 | Candidate windows must fall entirely within `earliest_start`–`latest_finish`. | ✅ Done |
| FR-14 | All slots in a candidate window must be strictly below `max_price` (pence/kWh). | ✅ Done |

### 3.3 Data Collection

| ID | Requirement | Status |
|---|---|---|
| FR-20 | The system SHALL fetch Octopus Agile half-hourly prices (pence/kWh inc. VAT) for the target day. | ✅ Done |
| FR-21 | The system SHALL fetch a daily weather summary (UV index, rain probability, max temp) for the target day. | ✅ Done |
| FR-22 | Price and weather clients SHALL use no API keys where possible (Octopus public endpoint, Open-Meteo free tier). | ✅ Done |

### 3.4 Event Memory

| ID | Requirement | Status |
|---|---|---|
| FR-30 | The system SHALL record a `laundry_completed` event when a user sends `/laundry_done`. | ✅ Done |
| FR-31 | Events SHALL be persisted to S3 as a JSON array and survive Lambda restarts. | ✅ Done |
| FR-32 | The `/events` command SHALL return the 10 most recent events with timestamps. | ✅ Done |
| FR-33 | The `/summary` command SHALL return the weekly laundry count and last completion time. | ✅ Done |
| FR-34 | The week definition SHALL be Monday 00:00 UTC → Sunday 23:59 UTC (ISO 8601). | ✅ Done |

### 3.5 Notifications

| ID | Requirement | Status |
|---|---|---|
| FR-40 | The system SHALL send a daily planning notification at 16:45 UTC with tomorrow's recommendation. | ✅ Done |
| FR-41 | The system SHALL send a morning reminder at 08:00 UTC with today's recommendation. | ✅ Done |
| FR-42 | The morning reminder SHALL re-evaluate prices (Agile may have repriced overnight). | ✅ Done |
| FR-43 | A recommended notification SHALL include the window, expected price, and reasons. | ✅ Done |
| FR-44 | A not-recommended notification SHALL include the reasons for declining. | ✅ Done |

### 3.6 Telegram Interface

| ID | Requirement | Status |
|---|---|---|
| FR-50 | `/health` SHALL return service version and status. | ✅ Done |
| FR-51 | `/laundry_done` SHALL record an event and confirm with this week's count. | ✅ Done |
| FR-52 | `/events` SHALL list recent events with timestamps. | ✅ Done |
| FR-53 | `/summary` SHALL show the weekly activity summary. | ✅ Done |

### 3.7 Registration & Access Control (Sprint A)

| ID | Requirement | Status |
|---|---|---|
| FR-60 | Registration SHALL be invite-only: `/start <code>` SHALL only begin onboarding when `<code>` matches the configured `HRSE_INVITE_CODE`. | ✅ Done |
| FR-61 | A missing or incorrect invite code SHALL NOT create any `ChatSettings` for that chat. | ✅ Done |
| FR-62 | **Invariant:** a chat is a daily-notification recipient if and only if it has a stored `ChatSettings` with `onboarding_complete: true`. No other state (group membership, language choice, a `TaskProfile`) confers recipient status. | ✅ Done |
| FR-63 | `/reset` SHALL clear `onboarding_complete` to `false`, removing the chat from notifications until it completes `/setup` again. | ✅ Done |
| FR-64 | An already-registered chat re-running `/start` SHALL NOT have its settings wiped; it SHALL be told to use `/reset` instead. | ✅ Done |

### 3.8 Per-Region Pricing (Sprint B)

| ID | Requirement | Status |
|---|---|---|
| FR-70 | Registration SHALL capture each chat's GSP pricing region via postcode lookup (Octopus's public grid-supply-points API), as the first `/setup` question. | ✅ Done |
| FR-71 | If postcode lookup fails (no match, ambiguous match, or the lookup API is unreachable), the chat SHALL be offered manual region selection (a 14-region button picker) as a fallback, or may resend a postcode to retry. | ✅ Done |
| FR-72 | A chat SHALL NOT be able to complete onboarding (`onboarding_complete: true`) without a resolved region. | ✅ Done |
| FR-73 | **Invariant:** the daily notification job SHALL fetch Agile prices at most once per distinct GSP region represented among that run's recipients — never once per chat, and never a single fetch shared across differing regions. | ✅ Done |
| FR-74 | A region whose price fetch fails SHALL NOT block notifications to chats in other regions; only that region's chats are skipped for the run. | ✅ Done |
| FR-75 | A regional tariff code SHALL only ever be built from a validated GSP letter (the real 14-letter set; `I`/`O` excluded) — never assembled from unvalidated input. | ✅ Done |

---

## 4. Non-Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| NFR-01 | Test coverage SHALL remain above 80% on `src/hrse`. | ✅ 98%+ |
| NFR-02 | All Python code SHALL pass `mypy --strict`. | ✅ Done |
| NFR-03 | All Python code SHALL pass `ruff check`. | ✅ Done |
| NFR-04 | Lambda execution roles SHALL follow least-privilege (no wildcard `*` IAM actions). | ✅ Done |
| NFR-05 | Secrets SHALL NOT be stored in environment variables or source control. | ✅ Done |
| NFR-06 | The S3 bucket SHALL have versioning enabled, AES256 encryption, and public access blocked. | ✅ Done |
| NFR-07 | The system SHALL run unattended for 30 days without manual intervention. | 🔜 Verify in prod |
| NFR-08 | All Lambda functions SHALL be instrumented with AWS X-Ray tracing. | ✅ Done |

---

## 5. Task Configuration

Default `LaundryTaskConfig` (hardcoded in `schedule_handler.py`, config-driven in future):

| Parameter | Default | Meaning |
|---|---|---|
| `target_runs_per_week` | `2` | Recommended weekly laundry runs |
| `duration_slots` | `4` | Run length in 30-min slots (4 = 2 hours) |
| `earliest_start` | `08:00` | No earlier than 08:00 UTC |
| `latest_finish` | `22:00` | Must finish by 22:00 UTC |
| `max_price` | `15.0p` | Only recommend slots below this price |
| `min_uv` | `3.0` | Only recommend when UV index is above this |
| `max_rain_probability` | `40%` | Only recommend when rain probability is below this |

---

## 6. Constraints

- Runtime: Python 3.12
- Cloud provider: AWS (eu-west-2)
- Infrastructure: Terraform ≥ 1.8
- Package manager: `uv`
- No external HTTP libraries (stdlib `urllib` only)
- No AI/LLM decision making in the engine

---

## 7. Future Extensibility

The plugin architecture is designed for additional tasks:

```
LaundryTask       ← implemented
DishwasherTask    ← planned
EVChargingTask    ← planned
CoolingTask       ← planned
```

Each task will implement the same `FlexibleTask` Protocol: `evaluate()`, `config()`, `recommendation()`. The `DecisionService` will dispatch to the appropriate task based on the event type.

---

## 8. Open Issues

- [ ] S3 read-modify-write has no concurrency control — fix with ETag conditional puts before adding concurrent Lambda invocations.
- [ ] `LaundryTaskConfig` is hardcoded — make config-driven (S3 JSON or env vars).
- [ ] Week definition is UTC-fixed — add `HRSE_TIMEZONE` for households in other timezones.
- [ ] No dead-letter queue on EventBridge rules — add for production reliability.
