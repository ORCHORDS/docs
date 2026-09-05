---
title: Agent Guardrail Bypass Testing
owner: ORCHORDS AI Governance
status: active
classification: internal
last-reviewed: 2026-09-05
review-cycle: quarterly
next-review: 2026-12-05
source: OWASP LLM Top 10 LLM01 Prompt Injection; MITRE ATLAS AML.T0051 LLM Plugin Compromise; NIST AI 600-1 §2.4 (Adversarial Robustness); Microsoft "Responsible AI Standard v2" §3.2 (Reliability & Safety Testing)
---

## Scope

Tests the layered guardrails that wrap an ORCHORDS agent — input filters, output filters, retrieval sanitization, tool-call validators, post-tool redaction — for bypass paths. A bypass exists when an actor can cause the agent to emit disallowed content, retrieve disallowed material, or invoke a disallowed tool even when the guardrail policy is in effect. Bypass discovery is the trigger for a guardrail defect ticket.

## Plan

1. Maintain a bypass probe library covering each guardrail tier independently: input, retrieval, tool-use, output, post-tool. Probes are versioned and reproducible.
2. Test the agent alone, the guardrail alone, and the integrated system. Bypass often lives in the seam between two defences.
3. For each bypass, classify severity: blocked content category × probable scale × exploit difficulty. Only high/critical bypasses block release.
4. Recompose a regression suite from every discovered bypass so future releases cannot regress to the bypass.
5. Run the canonical guardrail bypass corpus on every model swap, every retrieval index change, and every tool schema change.

## Inputs

- Guardrail configuration under `agents/guardrails/*.yaml`.
- Tool inventory and policy bindings from `agents/agent-manifest.json`.
- Bypass probe library at `agents/evals/guardrail-bypass/`.
- OWASP LLM Top 10 and ATLAS technique indexes.

## ORCHORDS Profile

| Dimension | Target |
|-----------|--------|
| Tier coverage | 5 / 5 (input, retrieval, tool, output, post-tool) |
| Probe cadence | weekly automated + on-demand for new tools |
| Critical-bypass blocking SLA | ≤ 24 h to mitigation or rollback |
| Regression suite size | ≥ 1 probe per documented bypass |
| Cross-team disclosure latency | ≤ 48 h to security@orchords |

## Implementation Notes

- A single failed probe is not always a defect — the probe may be malformed. Confirm with replay before opening a ticket.
- Avoid blindly adding more sensitive-keyword lists; misclassification grows faster than detection. Prefer embedding-classifier and structured-output validators.
- Bypass findings must include the transcript and the exact configuration version they ran against.
- Do not test against production traffic. Maintain a dedicated guardrail-test environment with disposable credentials.

## Companion Documents

- `AGENT_CONTENT_MODERATION_GATEWAY.md` — guardrail infrastructure.
- `AGENT_PROMPT_INJECTION_RED_TEAM_PROBES.md` — upstream of this testing.
- `AGENT_SAFETY_INCIDENT_TRIAGE.md` — when a probe indicates real-world exposure.
