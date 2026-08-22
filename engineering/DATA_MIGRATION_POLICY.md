---
title: "Data Migration Policy"
owner: "Engineering Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Data Migration Policy

## Purpose

Reduce integrity, privacy, compatibility, and rollback risk during material data changes.

## Requirements

Material migrations SHOULD define source and target expectations, validation rules, backup or recovery path, compatibility window, failure handling, observability, and ownership.

Migrations must preserve classification, retention, access-control, and privacy obligations unless an approved change explicitly modifies them.

## Verification

Use pre- and post-migration checks appropriate to risk. Important transformations should be reconcilable or sampled against expected outcomes.

## Rollback

When rollback is unsafe or infeasible, use staged migration, dual-read/write, immutable backup, reconciliation, or another controlled transition mechanism appropriate to the context.
