---
title: "Agent Hallucination Detection and Citation Faithfulness"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Hallucination Detection and Citation Faithfulness

## Scope

Defines how ORCHORDS agents detect hallucinations and verify citation faithfulness across retrieval, reasoning, and synthesis steps, so that the answers delivered to consumers are factually supported and traceable.

## Identifier table

| Field | Value |
|---|---|
| Topic | Hallucination detection and citation faithfulness for agents |
| Inputs | Model output, retrieved evidence, claim spans, citation graph |
| Outputs | Faithfulness score, hallucination flags, remediation actions |
| Audience | AI Platform, Knowledge Engineering, Service Owners |
| Trigger | Every retrieval-backed and tool-backed answer |
| Companion | AGENT_RETRIEVAL_GROUNDING_VERIFICATION.md, AGENT_EVALUATION_PATTERNS.md |

## Plan

1. Detect hallucinations at three layers: claim-to-evidence support, citation fidelity, and numerical consistency.
2. Compute a faithfulness score per answer by aggregating the per-claim support scores within the documented rubric.
3. Flag answers whose faithfulness score falls below the documented threshold for the query class.
4. For tool-backed answers, validate that any numerical or quoted claim can be traced back to a tool response field with the same value.
5. Block delivery of any answer that fails the threshold for a high-stakes query; rewrite or refuse according to the documented policy tier.
6. Track faithfulness trends by model revision, prompt revision, and retrieval snapshot; alert on regressions.
7. Maintain a held-out human-labeled set and periodically re-evaluate the faithfulness classifier against it.

## Inputs

- Claim spans and citation markers
- Retrieved evidence and tool response fields
- Faithfulness rubric and threshold table

## ORCHORDS Profile

| Metric | Threshold |
|---|---|
| Claim-to-evidence support | At least 0.90 cosine similarity on embedding; exact match on numerical claims |
| Citation fidelity | 100 percent of factual claims carry a citation |
| Numerical consistency | 100 percent of numerical claims match a tool response field or retrieved source |
| Faithfulness score | At least 0.92 for high-stakes queries; 0.80 otherwise |

## Implementation Notes

- Treat hallucination detection as a release gate; block deployments that regress the faithfulness score.
- Update the held-out labeled set whenever a new hallucination category is identified.

## Companion Documents

- AGENT_RETRIEVAL_GROUNDING_VERIFICATION.md
- AGENT_EVALUATION_PATTERNS.md
- AGENT_RED_TEAM_FINDING_TRIAGE.md
