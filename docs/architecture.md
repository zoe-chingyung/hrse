# HRSE — Architecture

> Status: **Timezone fix + Sprint 5A/5B/5C/A/B/C Complete**
> Last updated: 2026-08-07

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
│            │  schedule-handler   │◄── Octopus Agile API,           │
│            │  (Lambda)           │    once per recipient region    │
│            │                     │◄── Open-Meteo API (global)      │
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
│   │  /events /summary /prices   │──► S3 event store                │
│   │  /profile /reset /tasks     │──► S3 chat-settings store        │
│   │  button onboarding (callback_query: lang/region/task/cfg)      │
│   └─────────────────────────────┘                                  │
│                                                                     │
│   S3: hrse-{env}-state/events/household_events.json                │
│   S3: hrse-{env}-state/settings/{chat_id}.json  ← recipient source │
│   Secrets Manager: hrse/{env}/telegram (bot_token only)            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Inventory

| Component | Technology | Purpose |
|---|---|---|
| `schedule-handler` | AWS Lambda (Python 3.12) | Fetches prices (once per recipient GSP region) + weather, runs engine per chat/task, sends notifications |
| `telegram-handler` | AWS Lambda (Python 3.12) | Receives webhook commands, writes events, sends replies |
| EventBridge rules | Amazon EventBridge | Two cron schedules: 16:45 (planning) and 08:00 (reminder) |
| API Gateway HTTP API | Amazon API Gateway v2 | Exposes `POST /webhook` to Telegram |
| Event store | Amazon S3 | Household activity events as a JSON array |
| Chat-settings store | Amazon S3 | One `ChatSettings` JSON object per chat (`settings/{chat_id}.json`): language, per-task `profiles` dict, button-onboarding state (stage/queue/step), enabled tasks, GSP region code, completion flag. Source of truth for recipients (Sprint A), their pricing region (Sprint B), and their selected tasks (Sprint C). |
| Secrets | AWS Secrets Manager | `bot_token` only for Telegram (Sprint A: `chat_id`/`chat_ids` no longer read by the daily job) |
| Observability | Lambda Powertools + CloudWatch | Structured logging, X-Ray tracing |
| Infrastructure | Terraform | All resources versioned as code |

---

## 4. The Decision Engine

The `DecisionService` is a **pure Python service** — no AWS dependencies, fully unit-testable with in-memory stubs. It is generic over task type: `evaluate()` takes any `FlexibleTaskConfig`, not just laundry (see §13, "Task Registry").

### Inputs

| Input | Source | Shape |
|---|---|---|
| `WeeklySummary` | S3 event store via `WeeklyStateService` | `laundry_count`, `total_events` |
| `list[PricePoint]` | Octopus Agile API | `timestamp` (UTC), `price_pence` per 30-min slot |
| `DailyForecast` | Open-Meteo API | `uv_index`, `rain_probability`, `temperature_max` |
| `FlexibleTaskConfig` | `LaundryTaskConfig.from_profile_or_settings()` (see §14) for laundry; `TASK_REGISTRY[name]()` defaults for other tasks | Thresholds + constraints, structurally typed |

### Five Rules (evaluated in order)

```
Rule 1 — Target check
  laundry_count >= target_runs_per_week → NOT RECOMMENDED ("target met")
  NOTE: laundry_count is used for every task type — WeeklySummary has no
  per-task counts yet, so a dishwasher/EV target check is currently gated
  by the same laundry counter. Flagged as tech debt (README).

Rule 2 — Weather gate (day-level)
  config.weather_aware is False  → rule skipped entirely (dishwasher/EV —
                                    see §18, "Weather-Aware Gate")
  uv_index <= min_uv            → NOT RECOMMENDED ("UV too low")
  rain_probability >= max_rain  → NOT RECOMMENDED ("rain too high")

Rule 3 — Valid windows
  Build all runs of duration_slots consecutive 30-min slots
  inside earliest_start..latest_finish (parsed via parse_hhmm(), not a
  per-config convenience property — this is what keeps the engine generic)
  None found → NOT RECOMMENDED ("no valid window")

Rule 4 — Price filter
  Keep windows where avg_price * machine_kwh < wash_budget_pence
  None left → NOT RECOMMENDED ("no window below threshold")

Rule 5 — Rank
  Sort by total window cost (cheapest first)
  Tie-break: earliest start
  Return best candidate as RECOMMENDED
```

### Output

```python
Recommendation(
    task="laundry",              # from config.task_name — "laundry" / "dishwasher" / "ev_charging"
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
    │       WeeklyStateService.get_summary() → WeeklySummary   (household-wide)
    │
    ├─► DecisionService.evaluate(summary, prices, forecast, LaundryTaskConfig.from_settings())
    │       → global `recommendation`, used only for the response body / log line
    │
    └─► for each chat_id (or injected in tests via _chat_ids/_chat_id):
            ChatSettingsStore.list_all_chat_ids()             (Sprint A — paginated S3 listing
                │                                               under settings/, replacing the
                │                                               old Secrets Manager chat_ids)
                ├─► ChatSettingsStore.get(chat_id) for each candidate
                ├─► skip if settings is None or onboarding_complete is False
                │       (recipient invariant: completed ChatSettings == recipient;
                │        settings-load failures are treated as "not registered")
                └─► ChatSettings | None  for the surviving chat_ids
                │
                ├─► enabled_tasks = chat_settings.enabled_tasks or ["laundry"]
                ├─► _prices_for_chat(chat_settings, ...)   (Sprint B — see §17)
                │       region set  → that region's prices, fetched once and
                │                     cached for every chat sharing it
                │       no region  → the single global `prices` fetched above
                │       region fetch failed → None; chat is skipped this run
                ├─► for each task_name in enabled_tasks:
                │       "laundry"  → LaundryTaskConfig.from_profile_or_settings(profile, settings)
                │       otherwise → TASK_REGISTRY[task_name]()   (defaults only)
                │       DecisionService.evaluate(..., prices=chat_prices, ...) → Recommendation
                │
                ├─► display_tz = profile.timezone or HRSE_DISPLAY_TIMEZONE
                └─► NotificationService(display_tz).format_multi(recommendations, PLANNING)
                        HttpTelegramClient.send_message(chat_id, text)
                            → Telegram → that chat
```

`format_multi()` delegates to the original single-`Recommendation` `format()`
when a chat has exactly one enabled task (the default), so its output is
byte-identical to the pre-multi-task message.

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

**GSP region lookup** (Sprint B, onboarding only — never on the daily path):

| Property | Value |
|---|---|
| Endpoint | `/v1/industry/grid-supply-points/?postcode={postcode}` |
| Auth | None (public endpoint) |
| Response | `results: [{"group_id": "_C", ...}]` — strip the leading `_` for the region letter |
| Failure handling | Any no-match/ambiguous-match/error → `None`, never raises; caller falls back to manual region selection |

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
├── events/
│   └── household_events.json    # JSON array, oldest-first, append-only
└── settings/
    └── {chat_id}.json           # One ChatSettings object per chat
```

Example event log:
```json
[
  {"event_type": "laundry_completed", "timestamp": "2026-06-23T14:30:00.000Z"},
  {"event_type": "laundry_completed", "timestamp": "2026-06-25T09:15:00.000Z"}
]
```

`schedule_handler` derives its recipient list by listing every key under
`settings/` (`S3ChatSettingsStore.list_all_chat_ids()`, paginated) and
keeping only chats whose `ChatSettings.onboarding_complete` is `true` — see
§16.

**Week definition:** Monday 00:00:00 UTC (inclusive) → Sunday 23:59:59 UTC (inclusive), per ISO 8601.

---

## 8. Security

| Concern | Approach |
|---|---|
| Bot token | Stored in Secrets Manager; fetched at cold-start, cached in-process |
| Registration | Invite-only: `/start <code>` must match `HRSE_INVITE_CODE`, or no `ChatSettings` is created (see §16) |
| Lambda IAM roles | Least-privilege; scoped to specific S3 prefixes and one secret ARN |
| S3 bucket | Versioning enabled, AES256 encryption, all public access blocked |
| Webhook payload logging | `log_event=False` on telegram-handler to avoid logging user messages |
| Environment variables | `HRSE_INVITE_CODE` and other config live in Lambda env vars, not Terraform-managed secrets — treat the `.tfvars` value with the same care as a password |

Schedule Lambda IAM grants:
- `secretsmanager:GetSecretValue` on `hrse/{env}/telegram`
- `s3:GetObject`, `s3:PutObject` on `hrse-{env}-state/events/*`
- `s3:GetObject` (read-only) on `hrse-{env}-state/settings/*`
- `s3:ListBucket` on `hrse-{env}-state` (needed by `list_all_chat_ids()`'s paginated listing)

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
| `FlexibleTaskConfig` as a structural `Protocol`, not a base class | `DecisionService` depends on nothing task-specific; `LaundryTaskConfig`, `DishwasherConfig`, `EVChargingConfig` satisfy it without inheriting from it |
| `TaskProfile` fields mirror `LaundryTaskConfig` rather than embedding it | Keeps the persisted per-chat model decoupled from the engine's config type; `from_profile_or_settings()` is the one place that maps between them |

---

## 11. Known Limitations

| Issue | Impact | Planned fix |
|---|---|---|
| S3 read-modify-write with no concurrency control | Concurrent Lambda invocations could lose events | S3 conditional puts (ETag) or move events to DynamoDB |
| Rule 1 (target check) reads `WeeklySummary.laundry_count` for every task | A dishwasher/EV target check is gated by the laundry counter, not its own | Generalise events/`WeeklySummary` to per-task completion counts |
| ~~Every registered chat shares one global region~~ | ~~One tariff code for every recipient regardless of location~~ | ✅ Resolved (Sprint B) — see §17 |
| ~~`dishwasher`/`ev` have no onboarding or per-chat config~~ | ~~Only `TASK_REGISTRY` built-in defaults were used, chat-wide~~ | ✅ Resolved (Sprint C) — see §18 |
| EV has no deadline or kWh-based cost | Search spans the whole day; cost isn't estimated per charge session | Add once product decides the UX (deliberately deferred) |
| UTC-only week definition | Households far from UTC see slightly wrong week boundaries | Use `HRSE_DISPLAY_TIMEZONE` in `WeeklyStateService` |

---

## 12. Future Extensibility

The plugin architecture is now implemented (§13). Remaining extensibility work is the two gaps in §11 above — per-task activity tracking and per-task onboarding — plus new task types, which only require:

1. A new `_TaskConfigBase` subclass in `models/task_config.py` with sensible defaults.
2. A `TASK_REGISTRY` entry.
3. Optionally, an onboarding/env-config path if the task needs per-chat tuning (laundry is the only one with this today).

No changes to `DecisionService`, `NotificationService`, or `schedule_handler` are needed — they already operate generically over `FlexibleTaskConfig` and `ChatSettings.enabled_tasks`.

---

## 13. Task Registry (Sprint 5C)

`TASK_REGISTRY: dict[str, type[FlexibleTaskConfig]]` (in `models/task_config.py`) is the single source of truth mapping a task's registry key to its config class:

```python
TASK_REGISTRY = {
    "laundry": LaundryTaskConfig,
    "dishwasher": DishwasherConfig,
    "ev": EVChargingConfig,
}
```

Every entry is default-constructible (`Cls()`) — none of their fields are required — which is what lets `schedule_handler` build a config for any enabled task without task-specific wiring:

```python
config = LaundryTaskConfig.from_profile_or_settings(profile, settings) if name == "laundry" \
         else TASK_REGISTRY[name]()
```

`ChatSettings.enabled_tasks` is the per-chat list of registry keys to evaluate — set once, all at once, by the button multi-select picker during onboarding (§18); `/tasks` is a read-only view of it (no more `/add_task`/`/remove_task` — changing the set means `/reset`). `schedule_handler` evaluates one `Recommendation` per enabled task and `NotificationService.format_multi()` renders one message block per task (§5.1).

Note the two separate label vocabularies: `TASK_REGISTRY` keys (`"ev"`) are what Telegram commands operate on; `Recommendation.task` / `LaundryTaskConfig.task_name` values (`"ev_charging"`) are what the engine and notification blocks use. `EVChargingConfig.task_name` maps the former to the latter.

---

## 14. Per-Chat Profile Precedence Chain (Sprint 5B)

For the laundry task, three possible constraint sources are resolved by `LaundryTaskConfig.from_profile_or_settings(profile, settings)`:

```
chat has a TaskProfile (completed /setup)?
    │
    ├─ yes → build LaundryTaskConfig from the profile's fields
    │
    └─ no  → LaundryTaskConfig.from_settings(settings)
                 │
                 ├─ Settings has HRSE_* overrides? → use them
                 └─ otherwise → Settings field defaults
```

`TaskProfile` also carries two fields the engine doesn't consume directly: `outdoor_drying` (collected for a future weather-gate refinement) and `timezone` (consumed by the *display* layer — `/prices` and `NotificationService` prefer it over the global `HRSE_DISPLAY_TIMEZONE` — not by `DecisionService`).

`/setup` only asks 6 of `TaskProfile`'s fields (laundry target, earliest/latest, outdoor drying, timezone, wash budget); `duration_slots`, `machine_kwh`, `min_uv`, and `max_rain_probability` always come from the global `Settings` defaults, even for a chat with a profile.

---

## 15. Button Onboarding State Machine (Sprint C)

Telegram has no built-in multi-turn dialog state, so it's persisted on `ChatSettings` and driven entirely by inline-keyboard `callback_query` presses — free text is only accepted in two situations (postcode, and a config question's "Other" follow-up). The typed `/setup` conversation from Sprint 5B is gone; there's no `/add_task`/`/remove_task` either — task selection happens once, up front, as part of this flow.

### State fields

| Field | Meaning |
|---|---|
| `onboarding_stage` | `"postcode" \| "tasks" \| "config" \| None`. `None` means no onboarding conversation is active — this is what the router checks to decide whether plain text should go to `handle_onboarding_answer` instead of the unknown-command fallback. |
| `onboarding_step` | `0` while resolving the postcode/region; unrelated to per-task question progress. |
| `pending_task_selection` | Registry keys currently checked in the multi-select picker, before "Done" is pressed. Transient. |
| `pending_config_queue` | Registry keys still awaiting per-task config, in canonical `TASK_ORDER` (`laundry`, `dishwasher`, `ev`). `queue[0]` is the task currently being asked about. |
| `onboarding_task_step` | Index into `pending_config_queue[0]`'s question list (`_TASK_QUESTIONS[task_key]` in `telegram/commands.py`). |
| `awaiting_typed_field` | Set to a `TaskProfile` field name when its "Other" button was pressed; cleared once the typed answer lands. Only while this is set does plain text during the `"config"` stage get parsed as an answer. |

### Flow

```
/start <code> or /reset
    │
    ▼
handle_welcome() — bilingual language keyboard (lang:en / lang:zh)
    │  callback_query "lang:<code>"
    ▼
handle_language_callback() — saves language;
    if NOT onboarding_complete → _start_postcode_step()
    (a chat changing language via /language after finishing setup just gets
    the confirmation — no restart)
    │  stage="postcode"
    ▼
postcode text → _handle_postcode_answer()  (or region:<letter> callback
    on lookup failure — mirrors the language picker, see §17)
    │  region resolved → _start_task_selection()
    ▼
stage="tasks" — multi-select picker (🧺/🍽/🔌, one row each + "Done")
    │  callback_query "task:<key>" toggles pending_task_selection,
    │  redraws the same message via edit_message_text(..., reply_markup=...)
    │  callback_query "task_done":
    │      zero selected → re-show the picker with a warning (blocked)
    │      ≥1 selected   → create a default TaskProfile per task (in
    │                      TASK_ORDER), set enabled_tasks + profiles,
    │                      stage="config", pending_config_queue=selected
    ▼
stage="config" — per-task button questions, one task at a time
    │  callback_query "cfg:<field>:<value>" → parse, validate against
    │  TaskProfile, save, advance onboarding_task_step (or move to the
    │  next queued task, or finish)
    │  callback_query "cfg:<field>:other" → awaiting_typed_field=<field>,
    │  next plain-text message is parsed as that field's answer instead
    ▼
last question of last queued task answered
    │
    ▼
onboarding_complete=True, onboarding_stage=None — SETUP_COMPLETE_SUMMARY sent
```

### Per-task question tables

`_TASK_QUESTIONS: dict[str, tuple[_ButtonQuestion, ...]]` in `telegram/commands.py` holds one ordered tuple per registry key. Each `_ButtonQuestion` is `(field, message_key, options, parser, allow_other)`; `options` is `(button_label, value_string)` pairs where `value_string` is exactly what gets embedded in `callback_data` and handed to `parser` — so a button press and a typed "Other" answer for the same field go through the identical parse/validate path (`TaskProfile(**{**profile.model_dump(), field: value})`, which re-runs every field validator including the cross-field `latest_finish > earliest_start` check).

| Task | Questions | Notes |
|---|---|---|
| `laundry` | 9: target/week, duration, budget, earliest, latest, outdoor drying (buttons only, no "Other"), min UV, max rain, timezone | Full flow; `weather_aware=True` fixed, not asked |
| `dishwasher` | 6: target/week, duration, budget, earliest, latest, timezone | No weather questions; `weather_aware=False` fixed |
| `ev` | 1: charge duration (4h/6h/8h/10h → `duration_slots`, buttons only) | See §18 for why this is the only question |

A stale button press (from an earlier question or a task no longer at the front of the queue) is detected by comparing the callback's embedded field name against `_TASK_QUESTIONS[pending_config_queue[0]][onboarding_task_step].field`, and is a no-op (just acknowledged) on mismatch.

### The "ev" key vs "ev_charging" task_name guard

`_TASK_DISPLAY` and `_TASK_QUESTIONS` are always keyed by the `TASK_REGISTRY` key (`"ev"`) — never by `EVChargingConfig.task_name` (`"ev_charging"`), which only shows up in `Recommendation.task` / notification blocks (§13 documents the same split for the pre-existing `/tasks` command). Every onboarding lookup goes through the registry key; the split is called out explicitly in code comments at each lookup site since mixing the two up silently produces a `KeyError` or a blank label rather than a loud failure.

---

## 16. Registration & Recipient Gate (Sprint A)

**Invariant:** a completed `ChatSettings` object in S3 (`onboarding_complete: true`) *is* the definition of a registered recipient. Nothing else — being in a group, having picked a language, having a `TaskProfile` — grants that status.

```
/start <code>
    │
    ├─ existing ChatSettings has onboarding_complete=True?
    │       └─ yes → bilingual "already set up, use /reset" reply. No write.
    │
    ├─ code missing or != HRSE_INVITE_CODE?
    │       └─ yes → bilingual "invite-only" reply. No ChatSettings created.
    │
    └─ code correct → save ChatSettings(onboarding_complete=False, ...)
                        → handle_welcome() (bilingual welcome + language keyboard)
                            → language callback continues straight into the
                              button onboarding flow (§15)
                                → finishing the last selected task's config
                                  sets onboarding_complete=True
```

`/reset` clears `profiles`/`enabled_tasks`/`onboarding_complete` and restarts the button flow from the language picker, dropping the chat from notifications until it completes setup again (§15). The `/language` callback itself preserves whatever `onboarding_complete` was already when the chat has already finished onboarding — it only continues into the postcode step for a chat that hasn't; changing language after setup is complete never re-triggers registration.

**Fan-out (`schedule_handler`):**

```python
if _chat_ids is not None:
    chat_ids = _chat_ids            # test/ops injection — bypasses the gate below
elif _chat_id is not None:
    chat_ids = [_chat_id]           # test/ops injection — bypasses the gate below
else:
    chat_ids = [
        chat_id
        for chat_id in settings_store.list_all_chat_ids()
        if (settings := _safe_get_chat_settings(settings_store, chat_id)) is not None
        and settings.onboarding_complete
    ]
```

The `onboarding_complete` filter only applies to the store-derived path — `_chat_ids`/`_chat_id` are explicit test/ops overrides and have always bypassed the store entirely, same as before Sprint A.

`my_chat_member` (bot added to a group) still sends the bilingual welcome keyboard directly — it does **not** create or touch `ChatSettings`. A bot already sitting in a group will not re-fire `my_chat_member`, so someone must run `/start <code>` manually in that chat to register it.

`HRSE_INVITE_CODE` defaults to an empty string; `handle_start` treats an empty configured code as "registration always rejected" rather than "any code accepted", so an environment that hasn't set the variable can't be silently registered into.

---

## 17. Per-Region Grouped Price Fetch (Sprint B)

**Invariant:** Agile prices are fetched **once per distinct GSP region** among that run's recipients — never once globally for everyone, and never once per chat.

### Region capture (onboarding, one-time)

Button onboarding's `"postcode"` stage (§15) asks for a postcode right after language, before task selection:

```
postcode text
    │
    ├─► HttpOctopusClient.lookup_gsp(postcode)   (GET grid-supply-points/?postcode=...)
    │       one match  → region letter, e.g. "C"
    │       no/ambiguous match, or any error → None (never raises)
    │
    ├─ region found → save ChatSettings.octopus_region_code, advance to
    │                 the multi-select task picker (stage="tasks")
    │
    └─ region not found → send the 14-button region-picker keyboard
            (region:<letter> callback_query → handle_region_callback,
             mirrors the language picker) — or the user just resends a
             postcode to retry the lookup
```

The task multi-select picker and every per-task question only become reachable once the postcode stage hands off to `_start_task_selection()` (§15), so `onboarding_complete` can never become `True` without a region already set — structural enforcement (step ordering), not a separate runtime check.

### Fan-out (`schedule_handler`), grouped by region

```python
region_prices_cache: dict[str, list[PricePoint] | None] = {}

for chat_id in chat_ids:
    chat_settings = _safe_get_chat_settings(settings_store, chat_id)
    chat_prices = _prices_for_chat(
        chat_settings, prices, day_start, day_end,
        octopus_client_for_region, region_prices_cache,
    )
    if chat_prices is None:
        continue   # that region's fetch failed this run; already logged
    ...  # DecisionService.evaluate(..., prices=chat_prices, ...) per enabled task
```

- **No region set** (pre-Sprint-B or test-injected chats) → `chat_prices` is the single global `prices` fetched at the top of the handler (the same fetch that also drives the response-body summary) — this is what keeps every pre-Sprint-B test passing unchanged.
- **Region set** → `_fetch_region_prices` builds a tariff code (`build_regional_tariff_code(product_code, region_letter)`) and a fresh client (`build_octopus_client(tariff_code)`), fetches once, and caches the result (success *or* failure) in `region_prices_cache` keyed by region letter — a second chat in the same region never triggers a second fetch.
- **A region's fetch fails** (invalid letter, 404, any `OctopusApiError`) → logged, cached as `None`, and every chat in that region is skipped for this run with its own warning log. Other regions are unaffected — one bad region can't take down the whole job.

`build_octopus_client(tariff_code)` (in `clients/octopus.py`) is the uncached counterpart to the existing `get_octopus_client()` singleton — each region needs its own client instance since `HttpOctopusClient` is constructed with a fixed tariff code.

### Testability

`schedule_handler.handler()` gained `_octopus_client_for_region: Callable[[str], OctopusClientProtocol] | None`, parallel to the existing `_octopus` injection point. Tests inject a recording factory stub to assert "one fetch per region" and failure isolation without any network access; production omits it and falls back to `_real_octopus_client_for_region`, which is itself covered by one wiring test that mocks `urllib.request.urlopen` directly (see `tests/unit/test_schedule_handler.py::TestPerRegionPriceFetch`).

Weather stays a single global fetch (`WeatherClient.get_forecast`) — no per-region concept exists for it in this sprint.

---

## 18. Weather-Aware Gate & Shared Window Search (Sprint C)

### `weather_aware`

Pre-Sprint-C, dishwasher/EV disabled the weather gate implicitly, by defaulting `min_uv=0` and `max_rain_probability=100` so Rule 2's comparisons could (almost) never trip. Sprint C replaces that with an explicit `weather_aware: bool` field on both `TaskProfile` and every `FlexibleTaskConfig` (protocol member — see §13):

- `TaskProfile.weather_aware` defaults `True`; the button flow sets it once, at task-selection time, via `_default_profile_for_task()` — `True` for laundry, `False` for dishwasher/EV. It is never asked as a question; it's a property of the task type, not a user preference.
- `LaundryTaskConfig.weather_aware` defaults `True`; `DishwasherConfig`/`EVChargingConfig` default `False` at the class level, and `build_task_config()` forwards `profile.weather_aware` through for every task (laundry included) rather than special-casing it.
- `DecisionService._weather_failures()` returns `[]` immediately when `config.weather_aware` is `False` — the forecast is still passed in (schedule_handler fetches it once, globally, for every task) but is never read or required for a weather-blind task. The `reasons` list built for a recommended weather-aware-`False` task also drops the UV/rain lines, since they'd be misleading ("UV index above 0.0" reads like a real gate when there isn't one).

### EV's window search reuses the engine, not a bespoke algorithm

EV's onboarding question set is deliberately one entry: charge duration (§15), mapped straight to `TaskProfile.duration_slots`. No deadline, no kWh — per product decision, EV search spans the **whole day** rather than a fixed overnight slot: `_default_profile_for_task("ev")` sets `earliest_start="00:00"`, `latest_finish="23:30"` on the profile, which `build_task_config()` carries into the runtime `EVChargingConfig` exactly like any other field.

From there, EV asks nothing new of the decision engine. `DecisionService._candidate_windows()` (§4, Rule 3) already builds every contiguous `duration_slots`-length block of priced slots inside `earliest_start`..`latest_finish` and Rule 5 ranks them by total cost — this is the sliding-window cheapest-contiguous-block logic laundry and dishwasher already use; EV differs only in window length (from the duration button) and `weather_aware=False` (above). There is a similarly-named `_best_window()` helper in `services/price_chart.py`, but it belongs to a different feature entirely — it powers the `/prices` command's chart rendering, not recommendations, and `DecisionService` neither calls it nor shares code with it. Don't confuse the two: `_candidate_windows`/Rule 5 is the one path that actually produces `Recommendation`s for all three tasks.
