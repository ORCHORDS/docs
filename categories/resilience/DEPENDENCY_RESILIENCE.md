---
title: "Dependency Resilience"
owner: "Operations Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Dependency Resilience

## Purpose

Manage failure risk from internal and external dependencies required for material capabilities.

## Expectations

Critical dependencies SHOULD have understood failure modes, owners, recovery or substitution options, and monitoring appropriate to impact.

Resilience options may include graceful degradation, caching, alternate suppliers, queued work, manual fallback, isolation, data export, capacity reserve, or documented acceptance of downtime.

## Concentration

Multiple services using the same underlying provider, credential path, identity system, region, or operational team may share a hidden common-mode dependency. Assess effective concentration, not only vendor count.

## Review

Dependency assumptions should be revisited after incidents, major supplier changes, architecture changes, or evidence that recovery plans depend on an unavailable component.
