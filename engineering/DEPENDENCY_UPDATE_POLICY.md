---
title: "Dependency Update Policy"
owner: "Engineering Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Dependency Update Policy

## Purpose

Keep third-party components supportable and secure without turning updates into
unreviewed automatic change.

## Requirements

Dependencies SHOULD be:

- declared in reviewable manifests or equivalent records;
- version constrained or locked where reproducibility requires it;
- monitored for security and maintenance health;
- updated at a cadence appropriate to risk;
- removed when abandoned or no longer needed;
- evaluated for license and provenance concerns where material.

## Update priority

Urgency should consider exploitability, exposure, fix availability, breaking
change risk, dependency criticality, and compensating controls.

## Automation

Automated update proposals are useful, but merge decisions still require
appropriate verification. A passing build alone does not prove behavioral
compatibility.

See [Dependency Update SOP](../sop/DEPENDENCY_UPDATE_SOP.md).
