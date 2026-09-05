---
title: "ML Feature Freshness SLA"
owner: "Data Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# ML Feature Freshness SLA

## Scope

Defines how ORCHORDS sets, monitors, and enforces freshness SLAs for features used in online inference, so that downstream models do not silently produce low-quality predictions because of stale features.

## Identifier table

| Field | Value |
|---|---|
| Topic | Feature freshness SLAs and enforcement |
| Inputs | Feature catalog, online feature timestamps, consumer list |
| Outputs | Freshness SLA, violation report, consumer notification |
| Audience | Data Platform, AI Platform, Service Owners |
| Trigger | Every online inference request |
| Companion | ml-feature-store-schema-drift.md, ml-input-distribution-skew-monitor.md |

## Plan

1. Define a freshness SLA per feature: maximum age in seconds between feature production and feature consumption.
2. Validate the SLA against documented use cases; reject SLAs that exceed the use case tolerance.
3. Capture the production timestamp at the feature store and the consumption timestamp at the inference layer.
4. Track freshness per request and compute per-feature violation metrics over rolling windows.
5. Notify consumer owners of any feature whose violation rate exceeds the documented threshold.
6. Block deployment of any new consumer that depends on a feature with unresolved freshness violations.
7. Review freshness SLAs quarterly and after any documented context change.

## Inputs

- Feature catalog with freshness SLAs
- Online feature and inference timestamps
- Consumer inventory

## ORCHORDS Profile

| Use case class | Default SLA |
|---|---|
| Real-time personalization | 60 seconds |
| Real-time fraud detection | 5 seconds |
| Daily batch scoring | 24 hours |
| Long-horizon recommendation | 7 days |

## Implementation Notes

- Treat the freshness SLA as a release artifact for the feature; reject any feature without an SLA.
- Make freshness violation metrics visible to the consumer owner on the feature observability dashboard.

## Companion Documents

- ml-feature-store-schema-drift.md
- ml-input-distribution-skew-monitor.md
- ml-registry-promotion-gates.md
