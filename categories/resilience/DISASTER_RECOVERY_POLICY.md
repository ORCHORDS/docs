---
title: "Disaster Recovery Policy"
owner: "Operations Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Disaster Recovery Policy

## Purpose

Set company-wide recovery expectations for material technology and information
services without exposing private recovery architecture.

## Requirements

Material services MUST have recovery arrangements proportional to impact.
Those arrangements should cover:

- accountable recovery ownership;
- restoration priorities;
- dependencies and prerequisites;
- backup or reconstruction paths where applicable;
- integrity checks before restored service is trusted;
- communication and escalation;
- alternate procedures when the preferred path fails;
- evidence from periodic recovery tests.

Recovery documentation MUST be accessible to authorized responders during a
primary-system outage and MUST not depend on a single individual.

## Recovery decisions

During recovery, protecting people, information integrity, and containment of
security risk takes priority over restoring every feature quickly. A recovery
action that may destroy evidence or propagate corruption requires explicit
incident-command consideration.

## Testing

Recovery capability must be tested at a frequency based on impact and change
rate. Tests should verify more than backup existence: they should demonstrate
restoration, integrity, access, dependencies, and usable operating state.

See [Disaster Recovery Test SOP](../sop/DISASTER_RECOVERY_TEST_SOP.md).
