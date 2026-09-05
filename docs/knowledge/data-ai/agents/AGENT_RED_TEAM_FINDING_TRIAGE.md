---
title: "Agent Red Team Finding Triage"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Red Team Finding Triage

## Scope

Defines how ORCHORDS agents intake, classify, prioritize, and resolve findings from adversarial red team exercises so that vulnerabilities translate into concrete remediation work with owners and deadlines.

## Identifier table

| Field | Value |
|---|---|
| Topic | Triage workflow for agent red team findings |
| Inputs | Finding report, severity rubric, scope identifier, model card |
| Outputs | Triaged finding record, remediation ticket, closure evidence |
| Audience | AI Platform, Security, AIMS governance |
| Trigger | Receipt of a red team finding report |
| Companion | AGENT_SECURITY_TESTING_OWASP_LLM_GUIDANCE.md, AGENT_INCIDENT_RESPONSE_NIST_AI_PROFILE.md |

## Plan

1. Ingest the red team report and validate the scope: agent identifier, prompt revision, model revision, retrieval snapshot.
2. Reproduce each finding in a controlled environment; capture the exact prompt, retrieval result, and model response.
3. Classify severity using the documented rubric: critical, high, medium, low, informational, with explicit criteria per level.
4. Assign each finding to a remediation owner with a deadline derived from severity.
5. Open a remediation ticket linked to the finding and to the relevant controls in the agent's risk register.
6. Track remediation progress through verification: re-run the red team probe and confirm the vulnerability no longer reproduces.
7. Publish a quarterly trend report: findings opened, closed, average time to close by severity, and recurring categories.

## Inputs

- Red team report and probes
- Severity rubric
- Risk register and control mapping

## ORCHORDS Profile

| Severity | Remediation deadline | Verification |
|---|---|---|
| Critical | 7 days | Re-run probe plus independent review |
| High | 30 days | Re-run probe plus regression suite |
| Medium | 90 days | Re-run probe |
| Low | 180 days | Re-run on next planned exercise |
| Informational | Documented; no deadline | Tracked in the risk register |

## Implementation Notes

- Findings SHOULD reference the exact prompt revision and model revision so the fix can be traced back.
- Treat reproducibility as the first gate; unverifiable findings are downgraded to informational.

## Companion Documents

- AGENT_SECURITY_TESTING_OWASP_LLM_GUIDANCE.md
- AGENT_INCIDENT_RESPONSE_NIST_AI_PROFILE.md
- AGENT_MODEL_CHANGE_CONTROL_NIST_AI_RMF.md
