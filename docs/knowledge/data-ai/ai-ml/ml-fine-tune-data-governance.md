---
title: "ML Fine-Tune Data Governance"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# ML Fine-Tune Data Governance

## Scope

Defines the governance controls applied to datasets and prompts used to fine-tune ORCHORDS models, so that fine-tuning data meets the same consent, licensing, and quality standards as training data and can be audited end to end.

## Identifier table

| Field | Value |
|---|---|
| Topic | Governance controls for fine-tuning data |
| Inputs | Fine-tune dataset, base model, training plan, license record |
| Outputs | Governance attestation, fine-tune run record, audit evidence |
| Audience | AI Platform, Data Platform, Privacy, Legal |
| Trigger | Every fine-tune request |
| Companion | ml-dataset-card-provenance.md, ml-training-run-reproducibility.md |

## Plan

1. Require a dataset card for every fine-tune dataset, with the same validation rules as for training datasets.
2. Validate license compatibility between the dataset, the base model, and the intended downstream use; surface conflicts before the run starts.
3. Validate that the consent basis allows the documented downstream use; reject datasets without a documented basis.
4. Validate quality controls: deduplication, content filtering, sensitive content redaction, and documented provenance for any synthetic data.
5. Sign the fine-tune plan by the model owner, Privacy, and Legal before the run starts; reject unsigned plans.
6. Capture the fine-tune manifest with the same fields as a training run manifest, plus the dataset card reference and the consent attestation identifier.
7. Retain the fine-tune manifest and attestation for the documented retention period; make them queryable for audit.

## Inputs

- Fine-tune dataset and dataset card
- Base model identifier
- Fine-tune plan with intended use and license review

## ORCHORDS Profile

| Field | Validation |
|---|---|
| Dataset card | Present, not stale, not withdrawn |
| License | Compatible with base model license and intended use |
| Consent basis | Documented; matches intended use |
| Quality controls | Deduplication, content filtering, sensitive content redaction applied |
| Attestations | Model owner, Privacy, Legal signed |

## Implementation Notes

- Treat the fine-tune plan and the manifest as release artifacts; reject any run without them.
- Reject any fine-tune run whose base model license prohibits the intended downstream use.

## Companion Documents

- ml-dataset-card-provenance.md
- ml-training-run-reproducibility.md
- ml-model-card-completeness.md
