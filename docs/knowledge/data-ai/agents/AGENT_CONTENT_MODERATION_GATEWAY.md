---
title: "Agent Content Moderation Gateway"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Content Moderation Gateway

## Scope

Defines the content moderation gateway through which ORCHORDS agents pass inputs and outputs, so unsafe, harassing, or policy-violating content is detected, blocked, or rewritten before it reaches the user or downstream systems.

## Identifier table

| Field | Value |
|---|---|
| Topic | Centralized content moderation for agent inputs and outputs |
| Inputs | Prompt text, retrieved context, model output, tool output |
| Outputs | Moderation decision, rewritten content, refusal, escalation |
| Audience | AI Platform, Trust and Safety, Service Owners |
| Trigger | Every agent invocation |
| Companion | AGENT_OUTPUT_TOXICITY_CLASSIFIER_FALLBACK.md, AGENT_PROMPT_INJECTION_DEGRADATION_TESTS_OWASP.md |

## Plan

1. Apply input moderation at the gateway before any model call: classify for harassment, hate, self-harm, illicit behavior, and policy-specific categories.
2. Apply retrieval moderation on every retrieved document before it joins the prompt; reject or redact unsafe passages.
3. Apply output moderation on every model response before it reaches the user or downstream tool; rewrite or refuse unsafe responses.
4. Define a tiered response: pass, soft warning, hard rewrite, refusal, escalation.
5. Record moderation decisions in an audit log with prompt hash, response hash, decision, and reviewer override if any.
6. Sample moderation decisions for human review at a documented rate and feed findings back into category definitions.
7. Periodically evaluate the moderation classifier against the regression suite and against adversarial probes.

## Inputs

- Prompt text, retrieved context, model output
- Category definitions and review policies
- Override log

## ORCHORDS Profile

| Tier | Behavior |
|---|---|
| Pass | Continue without modification |
| Soft warning | Add a system-injected disclaimer; continue |
| Hard rewrite | Replace the offending span with a safe rewrite; record the original |
| Refusal | Return a refusal message; no further model call |
| Escalation | Page the on-call moderator; do not deliver the response |

## Implementation Notes

- Treat moderation as a hard gate; never bypass it in production.
- Version the category definitions and publish changes so callers can adapt.
- Avoid logging full unsafe content unless the audit retention policy explicitly authorizes it.

## Companion Documents

- AGENT_OUTPUT_TOXICITY_CLASSIFIER_FALLBACK.md
- AGENT_PROMPT_INJECTION_DEGRADATION_TESTS_OWASP.md
- AGENT_INCIDENT_RESPONSE_NIST_AI_PROFILE.md
