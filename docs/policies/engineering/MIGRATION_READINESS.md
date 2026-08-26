---
title: "Migration Readiness"
owner: "Engineering Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Migration Readiness

## Purpose

Reduce failure risk when changing schemas, formats, interfaces, dependencies, or operational state.

## Readiness criteria

Material migrations SHOULD define compatibility assumptions, validation method, failure/rollback path, observability, data-integrity checks, staged rollout where appropriate, ownership, and post-migration verification.

For irreversible changes, review must explicitly consider backup/restore, forward repair, partial-completion states, and how correctness will be demonstrated.

A migration is not complete merely because the change executed; intended data and service behavior must be verified.
