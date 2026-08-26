---
title: "Resilience Testing"
owner: "Operations Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Resilience Testing

## Purpose

Ensure continuity and recovery arrangements are exercised rather than treated
as documentation-only controls.

## Test types

Depending on risk, testing MAY include:

- tabletop exercises;
- backup restoration;
- dependency-loss scenarios;
- access-loss scenarios;
- failover or degraded-mode exercises;
- communication exercises;
- recovery from accidental or malicious data corruption;
- supplier or external-service disruption scenarios.

## Test quality

A useful test has a stated objective, assumptions, participants, success
criteria, evidence, observed gaps, accountable actions, and a closure check.

Tests SHOULD include realistic friction such as unavailable personnel,
incomplete information, or a failed primary recovery path when safe to do so.

## Findings

A failed exercise is valuable evidence. Findings must not be hidden to protect
a metric. Material gaps require tracked remediation or explicit risk
acceptance.

## Records

Use [Disaster Recovery Test Template](../templates/DISASTER_RECOVERY_TEST_TEMPLATE.md).
