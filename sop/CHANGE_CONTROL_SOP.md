---
title: "SOP: Change Control"
owner: "Operations Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# SOP: Change Control

## Trigger

Use before a material operational change or immediately after an emergency
change.

## Inputs

- change objective;
- owner;
- affected capability;
- risk/blast radius;
- test evidence;
- rollout and rollback plan;
- monitoring plan;
- required approvals.

## Procedure

1. Classify the change: standard, normal, high risk, or emergency.
2. Identify user, security, data, dependency, and availability impact.
3. Confirm prerequisites and dependencies.
4. Define success and stop conditions.
5. Define rollback or containment before execution.
6. Obtain the approval required by the change class.
7. Execute in the smallest safe increment.
8. Observe health and user-impact signals.
9. Stop or roll back when stop conditions are met.
10. Verify the intended outcome.
11. Record outcome and unexpected behavior.
12. If the change caused material impact, open the incident process.

## Evidence

Retain the change record, approval, verification result, and rollback outcome
when used.

## Emergency path

An emergency change may compress review but must have a named decision-maker,
a minimum safety check, and a retrospective record within two business days.
