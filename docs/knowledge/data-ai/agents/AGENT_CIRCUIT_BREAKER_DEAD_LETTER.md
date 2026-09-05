---
title: "Agent Circuit Breaker and Dead Letter Handling"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Circuit Breaker and Dead Letter Handling

## Scope

Defines how ORCHORDS agents trip circuit breakers on failing dependencies and route tasks to the dead letter queue, so that cascading failures are contained and recoverable work is not lost.

## Identifier table

| Field | Value |
|---|---|
| Topic | Circuit breakers and dead letter handling for agent dependencies |
| Inputs | Dependency identifier, error rate, retry budget, task payload |
| Outputs | Circuit state transitions, dead letter records, replay tooling |
| Audience | AI Platform, Reliability Engineering, Service Owners |
| Trigger | Every dependency call |
| Companion | AGENT_ERROR_RECOVERY.md, AGENT_RATE_LIMIT_PROPAGATION.md |

## Plan

1. Configure a circuit breaker per dependency with thresholds for error rate, latency, and consecutive failures.
2. On breach, transition the circuit to open and record the transition event with timestamp and reason.
3. While open, reject new calls immediately with a typed error; do not consume retry budget while open.
4. After the cooldown, transition to half-open and admit a probe call; close on success or reopen on failure.
5. For tasks whose calls were rejected, route the task to the dead letter queue with the original payload, the reason, and the dependency identifier.
6. Replay dead-lettered tasks once the dependency recovers; cap replays per task and alert on tasks that exceed the cap.
7. Surface circuit state and dead letter metrics on the agent health dashboard and page on sustained breaker activity.

## Inputs

- Dependency call outcomes and latency
- Retry budget and circuit thresholds
- Dead letter queue configuration

## ORCHORDS Profile

| Setting | Value |
|---|---|
| Error rate threshold | 50 percent over a rolling 60-second window |
| Consecutive failures threshold | 5 |
| Open cooldown | 30 seconds for general dependencies; 5 minutes for downstream databases |
| Half-open probes | 1 per cooldown |
| Dead letter replay cap | 3 attempts per task |

## Implementation Notes

- Treat circuit state as authoritative; the agent must not bypass it.
- Make dead letter payloads replayable in isolation; record sufficient context to reproduce the task.

## Companion Documents

- AGENT_ERROR_RECOVERY.md
- AGENT_RATE_LIMIT_PROPAGATION.md
- AGENT_OBSERVABILITY_DASHBOARD_AGENT_HEALTH.md
