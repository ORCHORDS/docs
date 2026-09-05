---
title: "ML Inference Budget Quota"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# ML Inference Budget Quota

## Scope

Defines how ORCHORDS sets, monitors, and enforces inference budget quotas per tenant, per model, and per request class, so that runaway traffic or expensive model revisions cannot exceed documented cost or compute envelopes.

## Identifier table

| Field | Value |
|---|---|
| Topic | Inference budget quota management |
| Inputs | Tenant identifier, model identifier, request class, pricing table |
| Outputs | Per-tenant quota, violation report, enforcement decision |
| Audience | AI Platform, FinOps, Service Owners |
| Trigger | Every inference request |
| Companion | ml-canary-rollback-criteria.md, ml-cold-start-traffic-ramp.md |

## Plan

1. Define a quota per tenant: requests per minute, requests per day, and cost per day.
2. Define a quota per model revision: requests per minute, GPU-minutes per hour.
3. Define a quota per request class: high-priority class, normal class, batch class.
4. Track quota usage per dimension; compute violation rate over rolling windows.
5. Apply enforcement: warn at soft threshold, reject at hard threshold, and degrade quality (smaller model, reduced retrieval) at overload threshold.
6. Notify tenant owners of any quota approaching exhaustion with at least 24 hours of notice.
7. Allow quota raise through documented FinOps approval; record the new quota and rationale.

## Inputs

- Quota table per dimension
- Live usage metrics
- FinOps approval records

## ORCHORDS Profile

| Dimension | Default quota |
|---|---|
| Tenant requests per minute | 600 |
| Tenant cost per day | 200 USD; configurable |
| Model GPU-minutes per hour | Per model instance; documented at deployment |
| Request class priority | High-priority class is metered separately from normal |

## Implementation Notes

- Treat the quota as a hard limit at the hard threshold; never allow it to be exceeded by application-level overrides.
- Make the quota decision auditable; record the tenant, the dimension, the decision, and the timestamp.

## Companion Documents

- ml-canary-rollback-criteria.md
- ml-cold-start-traffic-ramp.md
- ml-registry-promotion-gates.md
