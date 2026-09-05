---
title: "ML Dataset Card Provenance"
owner: "Data Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# ML Dataset Card Provenance

## Scope

Defines the provenance information required on every dataset card published by ORCHORDS, so that any model trained on the dataset can be audited for consent, licensing, and lineage.

## Identifier table

| Field | Value |
|---|---|
| Topic | Provenance metadata for ML datasets |
| Inputs | Source system, collection method, consent basis, license, retention |
| Outputs | Dataset card with required provenance sections and reviewers |
| Audience | Data Platform, Privacy, Legal, AI Platform |
| Trigger | Every new dataset registration, every major revision |
| Companion | ml-model-card-completeness.md, ml-fine-tune-data-governance.md |

## Plan

1. Define required sections: dataset identifier, version, source system or origin, collection method, consent basis, license, retention policy, owner, and review date.
2. Validate at registration that all required sections are present; reject registration otherwise.
3. Validate consent basis against the documented legal basis; reject datasets without a documented legal basis.
4. Validate license for compatibility with the intended use; surface conflicts to the dataset owner and Legal.
5. Validate retention policy against the privacy program record; reject retention that exceeds the documented policy.
6. Sign the dataset card by the data steward and by Privacy before it is published to model trainers.
7. Detect stale cards by comparing review date against the last collection change; flag any card older than the documented threshold.

## Inputs

- Source system and collection pipeline
- Consent capture record
- License and retention configuration
- Steward and Privacy attestations

## ORCHORDS Profile

| Section | Validation |
|---|---|
| Source and collection method | Non-empty; pipeline identifier where applicable |
| Consent basis | Required; must match one of the documented legal bases |
| License | Required; license identifier compatible with intended use |
| Retention policy | Required; matches privacy program record |
| Owner and review date | Owner present; review date within 90 days |

## Implementation Notes

- Reject any model registration that references a dataset card without a current Privacy attestation.
- Treat the dataset card as a release artifact signed by the data catalog.

## Companion Documents

- ml-model-card-completeness.md
- ml-fine-tune-data-governance.md
- ml-training-run-reproducibility.md
