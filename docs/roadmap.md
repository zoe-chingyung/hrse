# HRSE Roadmap

Version: 3.1

Status: Post-MVP Evolution — Sprints 5A/5B/5C complete (2026-07-29)

---

# What HRSE Is

HRSE began as a simple laundry recommendation bot built around Octopus Agile electricity pricing.

The long-term vision is significantly broader.

HRSE is a Household Decision Intelligence Platform.

Its purpose is to help households make better resource scheduling decisions by combining:

* Dynamic energy pricing
* Weather forecasts
* User constraints
* Historical behaviour
* Continuous feedback

HRSE does not automate appliances.

HRSE helps people decide when and how to use household resources efficiently.

---

# Core Architectural Principles

## Recommend, Not Control

HRSE never directly operates appliances.

The platform generates recommendations and schedules.

Users remain in control.

---

## Event-First Architecture

All meaningful actions become events.

Examples:

* RecommendationSent
* RecommendationAccepted
* RecommendationIgnored
* LaundryCompleted
* DishwasherCompleted
* EVChargingStarted

Events are immutable.

Business state is derived from events.

---

## Learn From Behaviour

HRSE should not rely exclusively on static configuration.

The system should gradually learn:

* Preferred activity windows
* Budget tolerance
* Weather preferences
* Recommendation acceptance patterns

The goal is adaptation, not automation.

---

## Infrastructure Independence

Decision logic must remain independent of:

* Telegram
* AWS
* S3
* DynamoDB
* Home Assistant

Infrastructure is replaceable.

Decision models are not.

---

## Plugin-Based Task Model

Laundry is the first task.

Future tasks include:

* Dishwasher
* EV Charging
* Tumble Dryer
* Oven Usage
* Battery Storage
* Heat Pump Scheduling

Every task participates in the same scheduling framework.

---

# Evolution Model

HRSE evolves through five maturity levels.

---

## Level 1 — Reactive Recommendations

Status: Complete

Inputs:

* Price
* Weather
* Weekly state

Output:

* Recommendation

Examples:

"Tomorrow 13:00–15:00 is a good laundry window."

---

## Level 2 — Personalised Recommendations

Status: Planned

Inputs:

* User Profile
* Price
* Weather
* Weekly state

Output:

* Personalised recommendation

Examples:

"Based on your preferred schedule, tomorrow 18:00–20:00 is the best laundry window."

---

## Level 3 — Behaviour Analytics

Status: Planned

New capability:

Observe recommendation outcomes.

Track:

* Recommendations sent
* Recommendations accepted
* Recommendations ignored

Produce:

* Acceptance rate
* Preferred hours
* Ignored hours
* Weekly behaviour summaries

Goal:

Understand user behaviour.

---

## Level 4 — Adaptive Scheduling

Status: Future

New capability:

Behaviour influences future recommendations.

Examples:

The system learns:

* User ignores midday recommendations
* User accepts evening recommendations
* User consistently exceeds wash budget

Future schedules adapt automatically.

Goal:

Improve recommendation quality.

---

## Level 5 — Reflective Intelligence

Status: Exploratory

Inspired by Memento-style learning systems.

The platform develops explicit observations and learnings.

Example:

Observation:

"Five consecutive afternoon recommendations were ignored."

Learning:

"Avoid recommending laundry between 12:00 and 15:00."

Decision models consume learnings as additional constraints.

Goal:

Move from recommendation generation to continuous optimisation.

---

# Delivery Roadmap

## Timezone fix — Notification display timezone

Status: Complete (2026-07-29)

Focus:

* `NotificationService` took a hardcoded BST offset; would render every
  notification an hour wrong once UK clocks went back in late October.

Outcome:

* `NotificationService(display_tz: ZoneInfo)` — label derived from
  `tzname()` at the window instant, correct on both sides of the DST
  boundary. Regression-tested with a winter (GMT) and summer (BST) case.

---

## Sprint 5A — Open Source Hardening

Status: Complete (2026-07-29)

Focus:

* Docker support
* Configuration externalisation
* Timezone correctness
* Developer experience
* Documentation

Outcome:

* Forkable project — `_DEFAULT_CONFIG` deleted; every laundry threshold is
  now an `HRSE_*` env var (`Settings` → `LaundryTaskConfig.from_settings()`).
  Docker support and the timezone fix landed alongside this sprint.

---

## Sprint 5B — User Onboarding Engine

Status: Complete (2026-07-29)

Focus:

* User profile model
* Telegram onboarding
* Settings management

Outcome:

* Non-technical users can configure HRSE via `/setup` — a 6-question
  Telegram conversation persisted as `ChatSettings.profile` (`TaskProfile`).
  `LaundryTaskConfig.from_profile_or_settings()` resolves precedence
  (profile → global `Settings` → field defaults). `/profile` and `/reset`
  round out the per-chat settings lifecycle.

---

## Sprint 5C — Plugin Architecture

Status: Complete (2026-07-29)

Focus:

* Generic task abstraction
* Task registry
* Dishwasher plugin
* EV charging plugin

Outcome:

* `FlexibleTaskConfig` — a structural `Protocol` capturing exactly the
  fields `DecisionService.evaluate()` reads — replaces the direct
  `LaundryTaskConfig` dependency. `DishwasherConfig` and `EVChargingConfig`
  satisfy it with no shared base class required by the engine.
  `TASK_REGISTRY` maps `laundry`/`dishwasher`/`ev` to their config classes;
  `ChatSettings.enabled_tasks` (default `["laundry"]`) drives which tasks
  `schedule_handler` evaluates per chat, and `/tasks`, `/add_task`,
  `/remove_task` manage that list from Telegram.
  `NotificationService.format_multi()` renders one block per enabled task,
  falling back to the original single-task `format()` output when only
  one task is enabled — existing chats see no change.
* Deliberately deferred (see the tech-debt table in `README.md`): per-task
  weekly-activity counts (Rule 1 still only tracks `laundry_count`), and
  onboarding/env-config for `dishwasher`/`ev` (they use `TASK_REGISTRY`
  defaults only). Sprint 6 (below) was explicitly out of scope for this
  delivery and was not started.

---

## Sprint 5D — Behaviour Analytics Layer

Focus:

* Recommendation outcome tracking
* Behaviour reporting
* Weekly summaries

New events:

* RecommendationSent
* RecommendationAccepted
* RecommendationIgnored

Outcome:

HRSE begins learning household behaviour.

---

## Sprint 6 — Adaptive Scheduler

Focus:

* Preference learning
* Time-window adaptation
* Behaviour-aware recommendations

Outcome:

Recommendations become personalised and self-adjusting.

---

## Sprint 7 — State Store Evolution

Focus:

* DynamoDB migration
* Query optimisation
* Event scalability

Outcome:

Support long-term behavioural history.

---

## Sprint 8 — Reflective Learning Engine

Focus:

* Observation generation
* Learning generation
* Constraint evolution

Pattern:

Observe
→ Remember
→ Reflect
→ Adapt

Outcome:

Self-improving scheduling intelligence.

---

## Sprint 9 — Home Energy Platform

Focus:

* Home Assistant integration
* Public API
* Mobile application

Outcome:

HRSE becomes a household decision platform.

---

# Long-Term Vision

HRSE is not a laundry bot.

HRSE is a continuously learning household scheduling engine.

The platform's purpose is to help households consume resources more intelligently over time by combining external signals, user preferences, historical behaviour, and adaptive decision models.

Laundry is simply the first plugin.
