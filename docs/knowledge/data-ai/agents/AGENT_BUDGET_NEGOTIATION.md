# Agent Budget Negotiation

## Scope

This article covers the patterns a collaborating agent or supervisor uses to declare, exchange, and reconcile resource budgets across the four dimensions that govern multi-agent workflows: tool-call count, token consumption, end-to-end latency, and monetary cost. It addresses the negotiation protocol between two parties — a delegator and a delegatee — when both have independent limits and no shared scheduler. It does not cover single-agent internal budgeting in isolation, nor does it address billing settlement, invoicing, or external payment-rail reconciliation. The article also assumes that budgets are advisory ceilings rather than access-control scopes: an exhausted budget should degrade quality or trigger refusal, not silently exceed limits.

Out of scope: ledgering of actual monetary transfers between organizations, procurement workflows, and contractual spend limits. These concerns are handled by procurement and finance systems; the agent must surface committed cost clearly enough for those systems to act, but should not absorb them.

## Implementation workflow

The delegator issues a budget envelope alongside the task. The envelope contains four numeric values (tool-call ceiling, token ceiling, latency ceiling, monetary ceiling), a budget version, a refusal policy that the delegatee must apply if any dimension is exhausted, and an optional `rebalance` channel that allows the delegatee to request more headroom mid-task. The envelope is encoded in the task payload itself so that downstream observers and replay systems can reproduce the negotiation without contacting the delegator.

On receipt, the delegatee performs a feasibility check: it projects the request against its own historical mean and tail latency for the requested tool mix and token profile. If the projection fits inside the envelope, the delegatee accepts and emits a `budget-accepted` receipt. If the envelope is infeasible, the delegatee returns a `budget-counter` proposing tighter or looser dimensions. The delegator either accepts the counter, rescopes the task, or abandons the delegation. This three-way handshake is symmetric with how OAuth scopes and audience negotiation operate in RFC 6749 and RFC 8707 — the negotiation is just-in-time and explicit.

Mid-task negotiation proceeds through a budget update channel. When the delegatee observes that a dimension is at risk of exhaustion (typically past 80 percent), it emits a `budget-warning` carrying observed usage and projected remaining. The delegator can either extend the envelope, request early termination, or downscope the remaining steps. The channel uses idempotent update keys so that retries and out-of-order warnings do not corrupt the running totals. All mid-task budget messages must be signed under the same task identity to prevent spoofed grant extensions.

Termination is decisive. When a dimension is exhausted, the delegatee stops work, returns the partial result with a `budget-exhausted` marker indicating which dimension triggered stop, and emits an evidence record describing work completed, work skipped, and any tool side effects that already occurred. The delegator treats the partial result as authoritative for completed steps and decides whether to retry under a new envelope, escalate to a human, or accept the partial outcome.

## Controls

Every budget envelope must carry an explicit `monotonic` flag and a freshness window; downstream parties reject envelopes whose version is stale or whose freshness window has elapsed. Numeric ceilings use fixed units — tool calls, tokens, milliseconds, and minor currency units (such as cents) — to avoid unit-conversion ambiguity across runtimes. Monetary ceilings are denominated explicitly; an envelope that lacks a currency code is rejected.

Cost and time are bound separately from authorization. An envelope that permits many tool calls does not widen the authority to invoke them; tool authorization is governed by the underlying OAuth scopes, MCP tool annotations, or capability tokens, not by the budget ceiling. The two systems must be auditable independently: one tells you what the agent was permitted to attempt, the other tells you what it could afford to attempt.

Budget enforcement must be observable. Each delegator emits `budget-declared`, `budget-accepted`, `budget-warning`, and `budget-exhausted` events. Each delegatee emits `budget-usage` heartbeats at a configured cadence (default every five seconds of wall time or every twenty percent of consumed budget, whichever is sooner). The events feed the same telemetry pipeline as trace spans so reviewers can correlate spend with behavior.

## Validation evidence

Verify negotiation with conformance tests that cover: acceptance under an infeasible envelope, counter-proposal under both directions, mid-task warning that triggers extension, mid-task warning that triggers termination, exhaustion that produces a partial result, and exhaustion that triggers a fresh envelope. Negative cases include spoofed budget updates, replayed counter-proposals, currency-unit mismatches, stale envelope versions, and unsigned update messages.

Operational evidence includes the complete chain of `budget-*` events for the task, signed receipts from both parties, observed usage versus projected usage at acceptance time, and the decision log showing why the envelope was extended, refused, or terminated. Telemetry must include the four dimensions as separate series so that a post-hoc reviewer can compute efficiency, not only total cost.

## Failure handling

When a budget message is dropped, delayed, or arrives out of order, the delegatee applies a fail-safe policy declared in the original envelope: either continue under the existing budget and emit a `budget-comm-failed` marker, or terminate immediately. The choice depends on operation sensitivity; high-cost or irreversible operations should default to termination on communication loss.

If the delegatee exhausts a budget dimension silently — that is, exceeds the ceiling without emitting the required marker — the delegator must treat the delegatee as misbehaving and revoke its task identity. The audit log of usage heartbeats makes silent overage detectable: a delegatee that has not reported usage cannot be trusted to self-report exhaustion.

When monetary or latency ceilings are mispriced — for example, when the delegatee's projection was wrong by an order of magnitude — the budget telemetry must support a post-mortem that distinguishes projection error from delegation misbehavior. The negotiator should treat mispricing as a calibration problem, not as a security violation, but must still produce a corrective update so the next envelope is sized correctly.

## Canonical sources

- RFC 6749, The OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- RFC 8707, Resource Indicators for OAuth 2.0: https://www.rfc-editor.org/rfc/rfc8707
- W3C WICG Budget API explainer (background reference for client-side budget primitives): https://wicg.github.io/budget-api/
- NIST AI 600-1, Artificial Intelligence Risk Management Framework: Generative AI Profile: https://www.nist.gov/itl/ai-risk-management-framework
