---
title: Agent Human-in-the-Loop Gating
owner: ORCHORDS AI Governance
status: active
classification: internal
last-reviewed: 2026-09-05
review-cycle: quarterly
next-review: 2026-12-05
source: NIST AI 600-1 Generative AI Profile §3.2 (Human-AI Configuration); ISO/IEC TS 8200:2024 AI Risk Management; EU AI Act 2024/1689 Art. 14 (Human Oversight); OECD AI Principles (2019, updated 2024) — Accountability
---

## Scope

Defines the gating conditions under which an ORCHORDS agent must pause for human review before executing an action, releasing output, or progressing to the next step. Gating is a first-class control: agents are not expected to self-attest beyond their permitted scope. The rules below specify what triggers a gate, who is the named approver, what evidence the approver sees, and how the decision is recorded.

## Plan

1. For every agent class, list the action categories that require prior approval: data egress beyond the host tenant, code execution in production namespaces, model or system prompt edits, externally visible artifact publication, financial transactions above policy threshold, and any action covered by regulatory obligation.
2. For each gated category, define the named approver role(s), the fallback approver chain, the SLA, and the evidence minimum (e.g. diff, citation, prior transcript).
3. Encode gating as a policy read by the agent at request time — never as soft-coded instructions inside a system prompt.
4. Record every gate invocation in the audit trail: agent, requested action, evidence presented, approver, decision, timestamp, and rationale if rejected.
5. Periodically sample previously approved gates for outcome review — does the action match the request, and was the agent's reasoning in the right neighborhood?
6. Recompose the gate catalogue on every policy release, every tool onboarding, and every regulatory update.

## Inputs

- Agent permission manifest.
- Approver directory (Slack/Teams/LDAP) and on-call schedule.
- Policy binder under `agents/policies/`.
- Audit log sink (read-only for approvers, write-once for the agent).

## ORCHORDS Profile

| Dimension | Target |
|-----------|--------|
| Gate coverage | all regulatorily relevant action categories |
| Gate decision SLA | ≤ 30 min during business hours, ≤ 4 h off-hours |
| Audit retention | ≥ 7 years |
| Approver rotation | monthly |
| Bypass policy | zero — no override path except documented emergency modes |

## Implementation Notes

- Never let the agent argue the user out of the gate. If the user is the approver, they must have the named role; otherwise the gate stays closed.
- Default to deny. If the agent cannot reach an approver within the SLA, the action is held, not executed.
- For regulated high-risk actions, require two named approvers (4-eyes). Single-approver modes are reserved for non-sensitive actions.
- The audit log entries must be cryptographically chainable so a future tampering attempt is detectable.

## Companion Documents

- `AGENT_HUMAN_HANDOFF_PROCEDURE.md` — same mechanism used reactively.
- `AGENT_SAFETY_INCIDENT_TRIAGE.md` — invoked when a gate is bypassed.
- `AGENT_CONTENT_MODERATION_GATEWAY.md` — gate for content output.
