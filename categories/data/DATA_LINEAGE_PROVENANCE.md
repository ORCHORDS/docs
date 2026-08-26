---
title: "Data Lineage and Provenance"
owner: "Data Governance Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Data Lineage and Provenance

## Purpose

Preserve enough context to understand where important data came from, how it changed, and what decisions depend on it.

## Requirements

For material datasets, lineage SHOULD identify authoritative source, key transformations, responsible processes or owners, significant derived outputs, and quality limitations appropriate to the use case.

## Risk

Lineage is especially important when data drives financial, security, compliance, user-facing, or AI decisions.

## Change control

Material transformation changes should be reviewable and validated. When lineage is uncertain, downstream users should not assume provenance or accuracy.

## Privacy

Lineage records should avoid unnecessary replication of personal or restricted data.
