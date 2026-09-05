---
title: "Agent Tool Use Audit Trail"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Tool Use Audit Trail

## Scope

Defines the audit trail required for every tool invocation made by ORCHORDS agents, so that downstream effects — state changes, side effects, sensitive reads — can be reconstructed, investigated, and attributed.

## Identifier table

| Field | Value |
|---|---|
| Topic | Audit trail requirements for agent tool invocations |
| Inputs | Tool identifier, arguments, response, identity context, decision rationale |
| Outputs | Immutable audit record, queryable by task and tool |
| Audience | AI Platform, Security, Service Owners, Audit |
| Trigger | Every tool invocation |
| Companion | AGENT_OBSERVABILITY_DASHBOARD_AGENT_HEALTH.md, AGENT_DISTRIBUTED_TRACING_OTEL.md |

## Plan

1. Emit an audit record at the start of every tool invocation with tool identifier, redacted arguments, identity context, and a documented rationale.
2. Emit a paired audit record at completion with response status, redacted response, duration, and resource identifiers affected.
3. Bind audit records to the agent task identifier and the model revision so they can be correlated across the lifecycle.
4. Persist audit records in immutable storage with retention aligned to the data classification of the affected resource.
5. Redact sensitive fields according to the data classification policy; never log raw credentials, secrets, or personal identifiers.
6. Provide a query interface that supports retrieval by task, by tool, by actor, and by affected resource.
7. Periodically sample audit records for completeness and feed findings back into the audit schema.

## Inputs

- Tool identifier and arguments
- Identity and authorization context
- Tool response and affected resource identifiers

## ORCHORDS Profile

| Field | Validation |
|---|---|
| Tool identifier | Required; matches the registered tool catalog |
| Arguments | Redacted per data classification |
| Decision rationale | Required for any state-changing tool |
| Response status | Required; success or documented failure mode |
| Affected resources | Required for state-changing tools |

## Implementation Notes

- Treat the audit trail as immutable; corrections require a new audit record, not edits.
- Make the audit schema versioned; bump the schema version on any breaking change.

## Companion Documents

- AGENT_OBSERVABILITY_DASHBOARD_AGENT_HEALTH.md
- AGENT_DISTRIBUTED_TRACING_OTEL.md
- AGENT_DELEGATED_AUTHORITY_RESPONSE.md
