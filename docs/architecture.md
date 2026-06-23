# HRSE – Architecture

> Status: **Draft** (Sprint 2B)
> Last updated: 2026-06-23

---

## 1. Overview

The **Household Resource Scheduling Engine (HRSE)** is a serverless, event-driven system that optimises the allocation of time-bound household resources—appliances, energy slots, and human tasks—across configurable time windows.

It runs entirely on AWS managed services, keeping operational overhead close to zero. Users interact via a Telegram bot.

---

## 2. High-Level Architecture

```
┌──────────────┐   HTTPS POST    ┌──────────────────────┐
│   Telegram   │ ─── webhook ──▶ │  API Gateway HTTP API │
│   (user)     │                 │  POST /webhook        │
└──────────────┘                 └──────────┬────────────┘
                                            │
                                 ┌──────────▼────────────┐
                                 │  telegram-handler     │
                                 │  (AWS Lambda)         │
                                 └──────────┬────────────┘
                                            │ route()
                              ┌─────────────▼────────────────┐
                              │  Command Router              │
                              │  /health /laundry_done       │
                              │  /events  /summary           │
                              └──────┬──────────────┬────────┘
                                     │              │
                          ┌──────────▼───┐  ┌───────▼────────────┐
                          │ Commands     │  │ WeeklyStateService  │
                          │ (reply text) │  │ (aggregation logic) │
                          └──────────────┘  └───────┬────────────┘
                                                    │ EventStore Protocol
                                         ┌──────────▼──────────┐
                                         │  S3EventStore       │
                                         │  s3://hrse-{env}-   │
                                         │  state/events/      │
                                         └─────────────────────┘
```

---

## 3. Component Inventory

| Component | Technology | Purpose |
|---|---|---|
| `telegram-handler` | AWS Lambda (Python 3.12) | Receives webhook, routes commands, sends replies |
| `schedule-handler` | AWS Lambda (Python 3.12) | EventBridge-driven schedule lifecycle (Sprint 2B+ stub) |
| API Gateway HTTP API | Amazon API Gateway v2 | Exposes `POST /webhook` to Telegram |
| Event store | Amazon S3 | Persists household activity events as JSON |
| Secrets | AWS Secrets Manager | Stores Telegram bot token (`hrse/{env}/telegram`) |
| Observability | Lambda Powertools + CloudWatch | Structured logging, X-Ray tracing |
| Infrastructure | Terraform | All resources versioned as code |

---

## 4. Event Memory Layer (Sprint 2B)

### 4.1 Data Model

```
Event
  event_type : str           # e.g. "laundry_completed"
  timestamp  : datetime UTC

WeeklySummary
  laundry_count           : int
  last_laundry_timestamp  : datetime | None
  total_events            : int
```

### 4.2 Storage Layout

```
s3://hrse-{environment}-state/
└── events/
    └── household_events.json   # JSON array, oldest-first
```

Example object content:
```json
[
  {"event_type": "laundry_completed", "timestamp": "2026-06-23T18:30:00Z"}
]
```

### 4.3 EventStore Protocol

All application code depends only on the `EventStore` Protocol:

```python
class EventStore(Protocol):
    def append_event(self, event: Event) -> None: ...
    def list_events(self) -> list[Event]: ...
```

`S3EventStore` is the production backend. Any class satisfying the Protocol can replace it (DynamoDB, local file, in-memory stub) without changing command handlers or services.

### 4.4 Week Definition

Monday 00:00:00 UTC (inclusive) → Sunday 23:59:59 UTC (inclusive), per ISO 8601.

### 4.5 Telegram Commands

| Command | Behaviour |
|---|---|
| `/health` | Returns service version and status |
| `/laundry_done` | Records `laundry_completed` event; confirms with weekly count |
| `/events` | Lists up to 10 most recent events, newest first |
| `/summary` | Shows weekly laundry count, last date, total events |

---

## 5. Data Flow — `/laundry_done`

1. User sends `/laundry_done` to Telegram bot.
2. Telegram POSTs the Update JSON to the API Gateway webhook URL.
3. API Gateway invokes `telegram-handler` Lambda.
4. Handler parses body → `TelegramUpdate`, passes to `router.route()`.
5. Router dispatches to `handle_laundry_done(chat_id, client, store)`.
6. `handle_laundry_done` creates `Event(event_type="laundry_completed")`.
7. `S3EventStore.append_event` downloads current JSON, appends, uploads.
8. `WeeklyStateService.get_summary` loads events, counts this week's laundry.
9. Reply is sent to Telegram via `HttpTelegramClient.send_message`.
10. Handler returns `{"statusCode": 200}` — Telegram acknowledges receipt.

---

## 6. Deployment Topology

| Environment | AWS Account strategy | Terraform state |
|---|---|---|
| `dev` | Shared dev account | Local / S3 backend (commented out) |
| `staging` | Shared staging account | S3 + DynamoDB lock |
| `prod` | Dedicated production account | S3 + DynamoDB lock |

---

## 7. Security Considerations

- Lambda execution roles follow least-privilege:
  - Telegram Lambda: `secretsmanager:GetSecretValue`, `s3:GetObject`, `s3:PutObject`, `s3:ListBucket` on the state bucket only.
- S3 state bucket: versioning enabled, AES256 encryption at rest, all public access blocked.
- Telegram bot token stored in Secrets Manager, fetched at cold-start, cached in-process.
- `log_event=False` on the Telegram handler to avoid logging webhook payloads.

---

## 8. Observability

- Structured JSON logging via Lambda Powertools with `child=True` loggers.
- AWS X-Ray tracing on the handler entry point.
- CloudWatch log groups with 30-day retention (managed by Terraform).

---

## 9. Key Design Decisions

| Decision | Rationale |
|---|---|
| `EventStore` as Protocol not ABC | Structural typing — test stubs require no inheritance |
| S3 JSON array over DynamoDB | Sufficient for v1 event volume; zero table management; human-readable |
| Read-modify-write on S3 | Simple and correct for single-Lambda concurrency model |
| `WeeklyStateService` has no AWS deps | Pure date arithmetic — fully testable with an in-memory stub |
| `store=None` guard in router | Keeps Sprint 2A `/health` path unaffected if store fails to initialise |
| Strict mypy | Catches type errors early; enforced in CI |

---

## 10. Open Questions

- [ ] Concurrent Lambda invocations could cause S3 write conflicts — evaluate S3 conditional writes or DynamoDB for Sprint 3.
- [ ] Week definition is fixed to UTC — consider household timezone support.
- [ ] Should events be partitioned per household ID once multi-household support is needed?
