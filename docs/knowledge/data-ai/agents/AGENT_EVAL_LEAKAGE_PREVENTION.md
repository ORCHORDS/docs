---
title: "Agent Eval Leakage Prevention"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Eval Leakage Prevention

## Scope

Defines how ORCHORDS agents prevent evaluation data, golden answers, or scoring rubrics from leaking into training, fine-tuning, prompt caches, or production prompt templates, so reported metrics remain trustworthy.

## Identifier table

| Field | Value |
|---|---|
| Topic | Separation between evaluation data and production data |
| Inputs | Eval dataset, training dataset, prompt template, cache layer |
| Outputs | Separation attestation, leakage scan report |
| Audience | AI Platform, Evaluation Lead, AIMS governance |
| Trigger | Any change in eval dataset, prompt template, or training pipeline |
| Companion | AGENT_FEW_SHOT_PROMPT_HYGIENE.md, AGENT_EVALUATION_DATA_PROVENANCE_NIST.md |

## Plan

1. Store evaluation datasets in a separate logical store with distinct access control and distinct encryption keys from production data.
2. Tag evaluation records with a non-removable marker so downstream scans can identify them.
3. Run a leakage scan over prompt templates, few-shot examples, fine-tuning datasets, and cache keys to ensure no eval record identifier appears.
4. Block any fine-tuning or prompt-template pull request that introduces an eval identifier into a production artifact; require explicit override with reviewer approval.
5. Validate that model provider fine-tuning exclusion lists include the eval dataset hash.
6. Track the lineage of every eval record to its origin and consent basis; refuse records without provenance.
7. Re-run the leakage scan after every prompt or fine-tuning revision and publish the result.

## Inputs

- Eval dataset identifiers and hashes
- Prompt template revisions
- Fine-tuning dataset identifiers
- Cache key namespaces

## ORCHORDS Profile

| Setting | Value |
|---|---|
| Eval store separation | Distinct account and project; distinct KMS keys |
| Leakage scan cadence | On every prompt or fine-tuning revision; weekly otherwise |
| Eval identifier marking | Tag plus prefix on every record |
| Override path | Two-person review with documented justification |

## Implementation Notes

- Treat the leakage scan as a release gate; do not allow releases that fail it without an override.
- Make the eval dataset hash part of the model card so it travels with the model.

## Companion Documents

- AGENT_FEW_SHOT_PROMPT_HYGIENE.md
- AGENT_EVALUATION_DATA_PROVENANCE_NIST.md
- AGENT_MODEL_PROVENANCE_ATTESTATION.md
