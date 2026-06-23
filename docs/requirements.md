# HRSE – Requirements

> Status: **Draft** (Sprint 2B)
> Last updated: 2026-06-23

---

## 1. Introduction

### 1.1 Purpose

This document captures the functional and non-functional requirements for the Household Resource Scheduling Engine (HRSE). It is the single source of truth for what the system must do.

### 1.2 Scope

HRSE manages the scheduling lifecycle of household resources within configurable time windows. It does not control physical devices directly; it produces schedules that downstream automation systems can consume.

### 1.3 Definitions

| Term | Definition |
|---|---|
| **Schedule** | A record that assigns one or more resources to a time window |
| **Resource** | A named, typed household entity (appliance, energy slot, person) |
| **Time window** | A half-open interval `[start, end)` expressed in UTC |
| **Household** | The top-level organisational unit; one household owns many schedules |

---

## 2. Stakeholders

| Stakeholder | Role |
|---|---|
| Household resident | Submits scheduling requests; consumes optimised schedules |
| Smart home platform | Publishes resource availability events; subscribes to schedule outputs |
| Engineering team | Develops and operates HRSE |

---

## 3. Functional Requirements

### 3.1 Schedule Management

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | The system SHALL accept a `ScheduleRequest` event containing a household ID, desired time window, and list of resources. | Must have |
| FR-02 | The system SHALL persist each schedule with a unique ID and creation timestamp. | Must have |
| FR-03 | The system SHALL support the following schedule status transitions: `PENDING → ACTIVE → COMPLETED` and `PENDING → CANCELLED`, `ACTIVE → CANCELLED`. | Must have |
| FR-04 | The system SHALL reject requests where the time window end is not strictly after the start. | Must have |
| FR-05 | The system SHALL publish a `ScheduleUpdated` event on every status transition. | Must have |

### 3.2 Resource Handling

| ID | Requirement | Priority |
|---|---|---|
| FR-06 | The system SHALL support three resource types: `APPLIANCE`, `ENERGY_SLOT`, `PERSON`. | Must have |
| FR-07 | A resource MUST have a non-empty name of at most 128 characters. | Must have |
| FR-08 | The system SHOULD detect resource conflicts within overlapping time windows and surface a conflict reason. | Should have |

### 3.3 Optimisation (Sprint 3+)

| ID | Requirement | Priority |
|---|---|---|
| FR-09 | When the `enable_optimiser` flag is `true`, the system SHOULD reorder resource assignments to minimise energy cost based on tariff data. | Should have |
| FR-10 | The optimiser MUST complete within the Lambda timeout (30 s) for schedules with up to 50 resources. | Must have (when FR-09 implemented) |

---

## 4. Non-Functional Requirements

### 4.1 Performance

| ID | Requirement |
|---|---|
| NFR-01 | End-to-end latency from event receipt to DynamoDB write MUST be < 500 ms at p99 under normal load. |
| NFR-02 | The system MUST handle at least 100 concurrent scheduling requests without throttling. |

### 4.2 Reliability

| ID | Requirement |
|---|---|
| NFR-03 | The system SHALL target 99.9% monthly uptime (≤ 43 min downtime/month). |
| NFR-04 | Failed Lambda invocations MUST be retried at least twice before routing to a dead-letter queue. |

### 4.3 Security

| ID | Requirement |
|---|---|
| NFR-05 | All inter-service communication MUST use TLS 1.2 or higher. |
| NFR-06 | Lambda execution roles MUST follow least-privilege; no wildcard `*` actions on IAM policies. |
| NFR-07 | Secrets MUST NOT be stored in environment variables or source control. |

### 4.4 Observability

| ID | Requirement |
|---|---|
| NFR-08 | Every Lambda invocation MUST emit a structured JSON log entry including `household_id`, `schedule_id`, and `request_id`. |
| NFR-09 | All Lambda functions MUST be instrumented with AWS X-Ray tracing. |

### 4.5 Maintainability

| ID | Requirement |
|---|---|
| NFR-10 | Test coverage MUST remain above 80% on the `src/hrse` package. |
| NFR-11 | All Python code MUST pass `mypy --strict` with no errors. |
| NFR-12 | All Python code MUST pass `ruff check` with no errors. |

---

## 5. Constraints

- Runtime: Python 3.12 only.
- Cloud provider: AWS (no multi-cloud requirement in v1).
- Infrastructure: Terraform; no CloudFormation or CDK.
- Package manager: `uv`; no `pip` or `poetry`.

---

## 6. Out of Scope (v1)

- Direct device control or integration with smart-home protocols (Z-Wave, Zigbee, Matter).
- Mobile or web front-end.
- Multi-tenant SaaS model (single household per deployment in v1).
- Real-time streaming (Kinesis); EventBridge is sufficient for v1 throughput.

---

## 7. Open Questions

- [ ] What is the maximum number of resources per schedule? (Informs DynamoDB item size and optimiser complexity.)
- [ ] Should `ScheduleRequest` events include a priority field for conflict resolution?
- [ ] Who owns tariff data for the optimiser — HRSE or an external service?

---

## 8. Sprint 2B — Event Memory Layer

### 8.1 Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-2B-01 | The system SHALL record a `laundry_completed` event when a user sends `/laundry_done`. | Must have |
| FR-2B-02 | Each recorded event SHALL include `event_type` (string) and `timestamp` (UTC datetime). | Must have |
| FR-2B-03 | The system SHALL persist events to Amazon S3 as a JSON array in the bucket `hrse-{env}-state`. | Must have |
| FR-2B-04 | The `/laundry_done` reply SHALL include the running laundry count for the current ISO week. | Must have |
| FR-2B-05 | The `/events` command SHALL return up to 10 most recent events, newest first. | Must have |
| FR-2B-06 | The `/summary` command SHALL return: laundry count, last laundry date, and total events for the current ISO week. | Must have |
| FR-2B-07 | The week definition SHALL be Monday 00:00 UTC (inclusive) to Sunday 23:59 UTC (inclusive). | Must have |
| FR-2B-08 | The event store backend SHALL be swappable via the `EventStore` Protocol without changing command handlers. | Must have |

### 8.2 Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-2B-01 | The S3 state bucket MUST have versioning enabled and all public access blocked. |
| NFR-2B-02 | The S3 state bucket MUST use AES256 server-side encryption. |
| NFR-2B-03 | Lambda IAM policy for S3 MUST be least-privilege: `GetObject`, `PutObject` on `events/*` prefix only; `ListBucket` on the bucket. |
| NFR-2B-04 | `WeeklyStateService` MUST have no direct AWS dependencies — it operates only on the `EventStore` Protocol. |
| NFR-2B-05 | Test coverage MUST remain above 80% after Sprint 2B additions. |

### 8.3 Constraints

- Event storage format is JSON array (human-readable, no schema migration tooling required for v1).
- Concurrent Lambda invocations writing simultaneously are not supported in v1 (single active invocation assumed).
- Only the `laundry_completed` event type is implemented in Sprint 2B. Additional event types land in future sprints.

### 8.4 Out of Scope (Sprint 2B)

- Octopus Energy integration.
- Weather data integration.
- Recommendation logic.
- Multi-household support.
- Event deletion or correction.
