---
title: "Feature Flag Lifecycle Governance"
owner: "Engineering Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-23"
review-cycle: "90 days"
next-review: "2026-11-21"
---

# Feature Flag Lifecycle Governance

## Purpose

Prevent temporary runtime controls from becoming permanent, undocumented complexity.

## Requirements

Material feature flags SHOULD identify owner, intended purpose, default state, affected risk, rollback role, expected removal or review trigger, and dependencies on experiments or releases.

Stale flags, unreachable branches, and permanently fixed states should be removed through normal change control.

Security- or privacy-sensitive flags require stronger review than ordinary presentation or rollout controls.
