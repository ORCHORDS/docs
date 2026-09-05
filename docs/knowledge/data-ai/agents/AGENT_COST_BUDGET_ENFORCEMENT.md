---
title: "Agent Cost Budget Enforcement"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Cost Budget Enforcement

## Scope

Defines how ORCHORDS agents enforce per-task and per-tenant cost budgets so that runaway loops, oversized contexts, or expensive tool calls cannot exceed declared spend envelopes.

## Identifier table

| Field | Value |
|---|---|
| Topic | Cost budget enforcement for agent invocations |
| Inputs | Token pricing tables, per-tenant budget policy, request metadata |
| Outputs | Per-task spend ledger, hard-stop decisions, alerts |
| Audience | Agent developers, FinOps, Service Owners |
| Trigger | Every agent invocation |
| Companion | AGENT_BUDGET_NEGOTIATION.md, AGENT_RETRY_BUDGETS.md |

## Plan

1. At task admission, look up the tenant budget policy: per-task cap, per-day cap, per-month cap, and soft-versus-hard enforcement.
2. Convert declared token limits and tool-call budgets into a remaining spend estimate using current pricing tables.
3. Record the budget decision in the per-task ledger so downstream steps can read remaining capacity.
4. Inject budget checkpoints after every step that may consume significant cost: large model calls, retrieval, image generation, and tool invocations priced per call.
5. On reaching the soft threshold, return a structured `budget.exceeded` warning to the agent and require it to downgrade or finalize.
6. On reaching the hard threshold, refuse further work and return a typed error; the orchestrator decides whether to escalate, abort, or resume in degraded mode.
7. Periodically reconcile ledger values against provider billing detail to catch pricing drift or missing usage records.

## Inputs

- Tenant and task identifier
- Model and tool call metadata
- Pricing tables refreshed on every billing cycle
- Soft and hard threshold configuration

## ORCHORDS Profile

| Setting | Value |
|---|---|
| Default per-task cap | Configurable per tenant; default 1.00 USD |
| Default per-day cap | 25.00 USD per tenant; auto-raise requires FinOps approval |
| Soft threshold | 80 percent of cap |
| Hard threshold | 100 percent of cap |
| Reconciliation cadence | Daily against provider billing; weekly against invoice |
| Pricing source | Vendor price sheet as the authoritative reference |

## Implementation Notes

- Store budget decisions in an append-only ledger so cost attribution is auditable.
- Treat soft threshold violations as warnings, not failures; the agent decides whether to continue.
- Treat hard threshold violations as failures; orchestrators must catch them and route through FinOps for raise or risk acceptance.
- Pricing tables are authoritative; never compute from a cached snapshot older than 24 hours.

## Companion Documents

- AGENT_BUDGET_NEGOTIATION.md
- AGENT_RETRY_BUDGETS.md
- AGENT_TOKENS_USAGE_TELEMETRY.md
