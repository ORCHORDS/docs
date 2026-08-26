---
title: "Data Quality and Integrity"
owner: "Data Governance Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Data Quality and Integrity

## Purpose

Define expectations for information whose accuracy or integrity materially
affects decisions, users, security, finance, or compliance.

## Requirements

Material data processes SHOULD define:

- authoritative source or ownership;
- validation appropriate to risk;
- error correction path;
- provenance where needed;
- protection against unauthorized change;
- reconciliation for important derived data;
- handling of incomplete or uncertain values.

## Decision use

A dataset suitable for one purpose may be unsuitable for another. Teams should
not infer accuracy, completeness, or representativeness merely because data is
available.

## AI use

Data used for AI evaluation or decision support also follows
[AI Data Governance](../ai/AI_DATA_GOVERNANCE.md).
