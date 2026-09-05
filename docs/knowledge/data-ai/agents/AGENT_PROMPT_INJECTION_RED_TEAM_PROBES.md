---
title: "Agent Prompt Injection Red Team Probes"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Prompt Injection Red Team Probes

## Scope

Defines how ORCHORDS designs, executes, and maintains a library of prompt injection red team probes so that the agent's defenses can be evaluated, regressed, and improved over time.

## Identifier table

| Field | Value |
|---|---|
| Topic | Red team probe library for prompt injection |
| Inputs | Probe categories, agent revision, evaluation harness, severity rubric |
| Outputs | Probe library, regression report, remediation tickets |
| Audience | AI Platform, Security, AIMS governance |
| Trigger | New agent revision, new prompt revision, scheduled probe refresh, regression finding |
| Companion | AGENT_RED_TEAM_FINDING_TRIAGE.md, AGENT_SECURITY_TESTING_OWASP_LLM_GUIDANCE.md |

## Plan

1. Define probe categories: direct injection, indirect injection via retrieved content, tool-output injection, multi-turn manipulation, jailbreak variants, and encoding or obfuscation tricks.
2. Maintain a versioned probe library with documented categories, expected agent behavior, and severity tag.
3. Run the probe library against the current agent revision in a controlled environment; capture inputs, retrieved content, tool calls, and model responses.
4. Score each probe against the documented expected behavior; classify the outcome as pass, partial, or fail.
5. Open remediation tickets for any failure and route them through the red team finding triage procedure.
6. Refresh probes on a documented cadence and add new probes from production incidents and external research.
7. Publish the regression report and the probe coverage table to governance.

## Inputs

- Probe library and category taxonomy
- Agent revision and prompt revision
- Severity rubric and expected behavior definitions

## ORCHORDS Profile

| Category | Required coverage |
|---|---|
| Direct injection | At least 20 probes per agent revision |
| Indirect injection | At least 20 probes per agent revision |
| Tool-output injection | At least 10 probes per agent revision |
| Multi-turn manipulation | At least 10 probes per agent revision |
| Encoding or obfuscation | At least 10 probes per agent revision |

## Implementation Notes

- Treat the probe library as evaluation data; apply the same leakage prevention controls as other eval datasets.
- Refresh probes whenever a new attack category is identified in the wild.

## Companion Documents

- AGENT_RED_TEAM_FINDING_TRIAGE.md
- AGENT_SECURITY_TESTING_OWASP_LLM_GUIDANCE.md
- AGENT_CONTENT_MODERATION_GATEWAY.md
