---
title: "Agent Retrieval Grounding Verification"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Retrieval Grounding Verification

## Scope

Defines how ORCHORDS agents verify that every claim produced by a model is grounded in retrieved evidence before it is shown to the user, so that ungrounded or fabricated claims are detected, rewritten, or refused.

## Identifier table

| Field | Value |
|---|---|
| Topic | Verification that model claims are grounded in retrieval |
| Inputs | Model output, retrieval identifiers, citation markers, evidence spans |
| Outputs | Grounding decision, rewritten or refused output, audit log |
| Audience | AI Platform, Knowledge Engineering, Service Owners |
| Trigger | Every model response with retrieved context |
| Companion | AGENT_HALLUCINATION_DETECTION_CITATION_FAITHFULNESS.md, AGENT_RETRIEVAL_SECURITY_BOUNDARY.md |

## Plan

1. Require every retrieval-backed answer to include per-claim citation markers tied to retrieval identifiers and span offsets.
2. Run a grounding check on the model output: align each claim to its cited span and confirm the citation actually supports the claim.
3. Classify each claim as grounded, partially grounded, or ungrounded using the documented rubric.
4. For ungrounded or partially grounded claims, decide on rewrite, refusal, or explicit warning based on the documented policy tier.
5. Record the grounding decision per claim in an audit log keyed by task identifier, model revision, and retrieval snapshot.
6. Reject any response that fails the grounding check for a high-stakes query class; allow soft warnings for general classes.
7. Sample a fraction of grounding decisions for human review and feed findings back into the rubric.

## Inputs

- Model output with citation markers
- Retrieval identifiers and span offsets
- High-stakes query class registry

## ORCHORDS Profile

| Decision | Behavior |
|---|---|
| All claims grounded | Deliver without modification |
| Partially grounded claims on a high-stakes query | Rewrite or refuse |
| Ungrounded claim | Refuse or rewrite; never deliver as fact |
| Missing citation on a factual claim | Treat as ungrounded |

## Implementation Notes

- Treat the citation marker format as part of the agent contract; refuse responses that lack markers for factual queries.
- Make the grounding check deterministic where possible; reserve learned classifiers for low-stakes cases.

## Companion Documents

- AGENT_HALLUCINATION_DETECTION_CITATION_FAITHFULNESS.md
- AGENT_RETRIEVAL_SECURITY_BOUNDARY.md
- AGENT_CONTENT_MODERATION_GATEWAY.md
