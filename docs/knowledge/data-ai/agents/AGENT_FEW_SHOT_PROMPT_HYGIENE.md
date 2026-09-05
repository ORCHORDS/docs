---
title: "Agent Few-Shot Prompt Hygiene"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Few-Shot Prompt Hygiene

## Scope

Defines how ORCHORDS agents curate, version, and validate few-shot examples embedded in prompts so demonstrations do not leak sensitive data, introduce bias, or bias model behavior unpredictably.

## Identifier table

| Field | Value |
|---|---|
| Topic | Few-shot example curation, review, and lifecycle |
| Inputs | Example corpus, prompt template version, classification labels |
| Outputs | Approved example set, review attestation, regression metrics |
| Audience | Prompt engineers, Knowledge Engineering, AIMS governance |
| Trigger | Initial prompt design, quarterly review, regression finding |
| Companion | AGENT_PROMPT_TEMPLATE_VERSION_LINEAGE.md, AGENT_EVAL_LEAKAGE_PREVENTION.md |

## Plan

1. Define the example schema: input, expected output, classification label, reviewer, and review date.
2. Curate an initial set from production traces only after explicit user consent, redaction, or synthesis from non-sensitive sources.
3. Review every example for sensitive content, including personal identifiers, secrets, and confidential business data; reject examples that fail review.
4. Label each example with the intended behavior it teaches and the failure mode it helps prevent.
5. Version examples alongside the prompt template so the lineage is auditable.
6. Measure the impact of each example on the regression suite; remove examples that do not improve any documented metric.
7. Rotate the example set on a documented cadence or whenever a regression is traced to a stale or biased example.

## Inputs

- Source traces with consent or synthesis provenance
- Prompt template version
- Regression suite output

## ORCHORDS Profile

| Setting | Value |
|---|---|
| Maximum examples per prompt | 8 for chat agents; 16 for batch extraction |
| Review attestation cadence | Every 90 days or on regression |
| Sensitive content detection | DLP scanner plus manual review for borderline cases |
| Bias review | Spot check by a second reviewer against the bias fairness probing checklist |

## Implementation Notes

- Never embed live customer data in few-shot examples without explicit, recorded consent.
- Document the intent of every example; an unlabeled example is a maintenance liability.
- Treat examples as part of the prompt lineage; the same retention and access controls apply.

## Companion Documents

- AGENT_PROMPT_TEMPLATE_VERSION_LINEAGE.md
- AGENT_EVAL_LEAKAGE_PREVENTION.md
- AGENT_BIAS_FAIRNESS_PROBING.md
