---
title: "Runbook Management"
owner: "Operations Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Runbook Management

## Purpose

Keep operational procedures usable during time-sensitive work.

## Requirements

Material runbooks SHOULD identify trigger, scope, prerequisites, safe diagnostic steps, decision points, rollback or stop conditions, escalation, evidence, and completion criteria.

## Safety

Do not embed production credentials, recovery secrets, private keys, or unnecessary sensitive topology in broadly accessible runbooks.

Commands or actions with destructive impact should be clearly marked and guarded by verification steps.

## Maintenance

Review runbooks after material incidents, tooling changes, ownership changes, or repeated operator confusion. A runbook that is not tested or used may be stale even when its review date is current.
