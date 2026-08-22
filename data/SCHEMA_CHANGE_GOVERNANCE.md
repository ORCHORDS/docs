---
title: "Schema Change Governance"
owner: "Data Governance Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-23"
review-cycle: "90 days"
next-review: "2026-11-21"
---

# Schema Change Governance

## Purpose

Control material changes to data structures so producers, consumers, migrations, retention, and quality controls remain aligned.

## Requirements

Material schema changes SHOULD identify owner, affected fields or semantics, compatibility impact, migration needs, downstream consumers, validation, and rollback or forward-repair strategy.

Renaming or retyping data without preserving meaning can be a breaking change even when storage succeeds.
