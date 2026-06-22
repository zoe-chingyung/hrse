# HRSE – Architecture

> Status: **Draft** (Sprint 1)  
> Last updated: 2026-06-22

---

## 1. Overview

The **Household Resource Scheduling Engine (HRSE)** is a serverless, event-driven system that optimises the allocation of time-bound household resources—appliances, energy slots, and human tasks—across configurable time windows.

It runs entirely on AWS managed services, keeping operational overhead close to zero.

---

## 2. High-Level Architecture

```
┌─────────────┐     EventBridge      ┌──────────────────────┐
│  Client /   │  ScheduleRequest  ──▶│  schedule-handler    │
│  IoT Device │                      │  (AWS Lambda)        │
└─────────────┘                      └──────────┬───────────┘
                                                │
                                    ┌───────────▼───────────┐
                                    │   ScheduleService     │
                                    │   (business logic)    │
                                    └───────────┬───────────┘
                                                │
                             ┌──────────────────▼──────────────────┐
                             │                                     │
                  ┌──────────▼──────────┐          ┌──────────────▼──────┐
                  │   DynamoDB          │          │  EventBridge (out)  │
                  │   (schedule state)  │          │  (downstream events)│
                  └─────────────────────┘          └─────────────────────┘
```

---

## 3. Component Inventory

| Component | Technology | Purpose |
|---|---|---|
| `schedule-handler` | AWS Lambda (Python 3.12) | Entry point; validates and routes schedule lifecycle events |
| Schedule state store | Amazon DynamoDB (on-demand) | Persists schedule records and status transitions |
| Event bus | Amazon EventBridge | Decouples producers and consumers; drives Lambda triggers |
| Observability | AWS Lambda Powertools (Logger, Tracer) + CloudWatch | Structured logging and X-Ray tracing |
| Infrastructure | Terraform | All resources are defined and versioned as code |

---

## 4. Data Flow

1. A client or IoT device publishes a `ScheduleRequest` event to the HRSE EventBridge bus.
2. An EventBridge rule matches the event and triggers `schedule-handler` Lambda.
3. The handler validates the payload and calls `ScheduleService`.
4. `ScheduleService` writes/updates the schedule record in DynamoDB.
5. On significant state transitions, an outbound event is published back to EventBridge for downstream consumers.

---

## 5. Deployment Topology

| Environment | AWS Account strategy | State backend |
|---|---|---|
| `dev` | Shared dev account | S3 + DynamoDB lock |
| `staging` | Shared staging account | S3 + DynamoDB lock |
| `prod` | Dedicated production account | S3 + DynamoDB lock |

All environments are deployed from the same Terraform root module, parameterised by the `environment` variable.

---

## 6. Security Considerations

- Lambda execution roles follow least-privilege: each function gets only the DynamoDB and EventBridge permissions it needs.
- Secrets (e.g., API keys) are stored in AWS Secrets Manager and injected at runtime — never in environment variables or source control.
- All data in transit uses TLS; DynamoDB tables are encrypted at rest with AWS-managed keys (can be upgraded to CMK in prod).
- IAM permission boundaries will be applied to all roles in the `prod` account.

---

## 7. Observability

- **Structured logging**: Lambda Powertools JSON logger with correlation IDs.
- **Distributed tracing**: AWS X-Ray via Lambda Powertools Tracer.
- **Metrics**: Lambda Powertools Metrics emits custom CloudWatch metrics per operation.
- **Alerting**: CloudWatch Alarms on Lambda error rate and duration (configured in Sprint 3).

---

## 8. Key Design Decisions

| Decision | Rationale |
|---|---|
| Serverless (Lambda) over containers | Zero infrastructure management; pay-per-invocation suits bursty household scheduling workloads |
| EventBridge as event bus | Native AWS integration; schema registry support for contract enforcement |
| DynamoDB over RDS | Predictable latency; schedule records map naturally to a key-value model |
| Python 3.12 | `StrEnum` and improved performance; strong AWS SDK / Powertools support |
| uv package manager | Fast dependency resolution; reproducible lockfiles; native `pyproject.toml` support |
| Strict mypy | Catch type errors early; improves maintainability as the codebase grows |

---

## 9. Open Questions (Sprint 1)

- [ ] Define the exact DynamoDB access patterns (PK/SK design, GSIs required).
- [ ] Decide on EventBridge bus — custom bus vs. default bus.
- [ ] Confirm whether schedules need a FIFO queue (SQS) in front of Lambda for back-pressure.
- [ ] Multi-region requirements for `prod`?
