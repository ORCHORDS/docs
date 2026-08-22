---
title: "Release Rollback Policy"
owner: "Release Manager"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Release Rollback Policy

## Purpose

Ensure material releases have a realistic containment or reversal strategy.

## Requirements

Before a high-impact release, the release owner SHOULD know:

- rollback or disable path;
- data migration reversibility;
- compatibility constraints;
- monitoring signals that trigger rollback;
- authority to make the decision;
- communication path;
- recovery actions if rollback itself fails.

## Irreversible changes

When rollback is not feasible, use staged rollout, compatibility windows,
feature controls, backups, parallel paths, or other risk-reduction mechanisms
as appropriate.

## Decision quality

Rollback criteria should be outcome-based. Teams should not continue a harmful
release merely to avoid admitting a failed deployment.

See [Release SOP](../sop/RELEASE_SOP.md).
