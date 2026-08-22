---
title: "SOP: Release"
owner: "Release Manager"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# SOP: Release

## Preconditions

A release candidate exists and required change review is complete.

## Procedure

1. Freeze the intended scope.
2. Verify required CI checks and test evidence.
3. Review unresolved security findings and approved exceptions.
4. Confirm migration, rollout, rollback, and monitoring plans.
5. Confirm artifact identity and integrity.
6. Prepare accurate release notes.
7. Obtain release approval.
8. Promote using the approved mechanism.
9. Verify health and critical user journeys.
10. Monitor through the defined observation window.
11. Roll back or contain if stop conditions are reached.
12. Record release outcome and follow-up.

## Evidence

Retain source revision, artifact digest where applicable, check results,
approval, promotion time, and rollback/verification outcome.

## Emergency release

Use the emergency change path in
[Change Control SOP](./CHANGE_CONTROL_SOP.md), then complete missing evidence
retrospectively.
