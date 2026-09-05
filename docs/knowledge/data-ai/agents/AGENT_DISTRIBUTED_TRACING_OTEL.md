---
title: "Agent Distributed Tracing with OpenTelemetry"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Distributed Tracing with OpenTelemetry

## Scope

Defines how ORCHORDS agents emit distributed traces using OpenTelemetry so that latency, retries, and tool calls can be analyzed end to end and correlated with platform traces.

## Identifier table

| Field | Value |
|---|---|
| Topic | OpenTelemetry tracing for agent invocations |
| Inputs | Task identifier, model identifier, tool identifier, span events |
| Outputs | Trace spans, dashboards, alerts |
| Audience | AI Platform, Reliability Engineering, Service Owners |
| Trigger | Every agent invocation and step |
| Companion | AGENT_OBSERVABILITY_DASHBOARD_AGENT_HEALTH.md, AGENT_TOOL_USE_AUDIT_TRAIL.md |

## Plan

1. Initialize a root span for each agent task with task identifier, tenant identifier, agent identifier, and model revision as attributes.
2. Emit child spans for every model call, retrieval call, and tool call with documented attributes and consistent naming.
3. Propagate trace context across tool boundaries using documented propagation headers.
4. Record retry attempts as span events with the documented retry policy identifier and attempt number.
5. Sample traces with documented rates per environment and per query class; never sample out security-relevant spans.
6. Aggregate traces into per-agent and per-tool dashboards with latency, error rate, and retry rate as primary signals.
7. Alert on regressions against the documented SLO per agent and per tool.

## Inputs

- Task identifier and tenant identifier
- Model and tool identifiers
- Trace context and span events

## ORCHORDS Profile

| Setting | Value |
|---|---|
| Default sampling rate | 100 percent in pre-production; 10 percent in production |
| Security-relevant span rate | 100 percent always |
| Span naming convention | `agent.step.<kind>` |
| Required attributes | tenant, agent, model_revision, tool_revision, prompt_revision |

## Implementation Notes

- Treat the trace schema as versioned; coordinate schema changes with downstream dashboards.
- Propagate context to upstream callers so platform-level traces correlate with agent traces.

## Companion Documents

- AGENT_OBSERVABILITY_DASHBOARD_AGENT_HEALTH.md
- AGENT_TOOL_USE_AUDIT_TRAIL.md
- AGENT_STREAMING_BACKPRESSURE.md
