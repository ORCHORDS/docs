---
title: "Agent Observability Dashboard and Agent Health"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Observability Dashboard and Agent Health

## Scope

Defines the observability dashboard and the agent health model used by ORCHORDS so that operators can monitor agents in real time and detect regressions in quality, latency, cost, or safety.

## Identifier table

| Field | Value |
|---|---|
| Topic | Observability dashboard and health model for agents |
| Inputs | Trace data, audit records, error events, business metrics |
| Outputs | Dashboards, alerts, health score |
| Audience | AI Platform, Reliability Engineering, Service Owners |
| Trigger | Continuous |
| Companion | AGENT_DISTRIBUTED_TRACING_OTEL.md, AGENT_TOOL_USE_AUDIT_TRAIL.md |

## Plan

1. Define the health model dimensions: success rate, latency, cost, faithfulness, refusal rate, handoff rate, and circuit breaker activity.
2. Aggregate each dimension into a health score per agent with documented weights; surface the score on the dashboard.
3. Define SLOs per dimension per agent class; alert on sustained breaches.
4. Provide drill-down from the dashboard to traces, audit records, and conversation history.
5. Track health scores across model revisions, prompt revisions, and retrieval snapshots; alert on regressions.
6. Surface the dashboard to on-call, Service Owners, and AIMS governance with documented access controls.
7. Review the health model quarterly and update weights and SLOs in line with observed behavior.

## Inputs

- Trace and metric streams
- Audit records and error events
- Health model weights and SLO targets

## ORCHORDS Profile

| Dimension | Default weight | Default SLO |
|---|---|---|
| Success rate | 0.25 | At least 0.95 over rolling 24 hours |
| Latency p95 | 0.15 | Within documented target per agent |
| Cost per task | 0.15 | Within documented budget |
| Faithfulness | 0.20 | At least 0.92 for high-stakes classes |
| Refusal rate | 0.10 | Within documented band per agent |
| Handoff rate | 0.10 | Within documented band per agent |
| Circuit breaker activity | 0.05 | No sustained open circuits |

## Implementation Notes

- Treat health score as a derived metric; the underlying metrics remain the authoritative inputs.
- Document any change to weights or SLOs in the model change log.

## Companion Documents

- AGENT_DISTRIBUTED_TRACING_OTEL.md
- AGENT_TOOL_USE_AUDIT_TRAIL.md
- AGENT_CONTENT_MODERATION_GATEWAY.md
