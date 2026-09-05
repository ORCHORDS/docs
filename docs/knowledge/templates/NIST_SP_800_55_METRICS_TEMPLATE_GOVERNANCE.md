---
title: "NIST SP 800-55 Performance Measurement Guide for Information Security Template Governance"
standard: "NIST SP 800-55 Rev 1 (Performance Measurement Guide for Information Security)"
publisher: "National Institute of Standards and Technology"
category: "governance-template"
subcategory: "security-measurement-and-metrics"
canonical_url: "https://csrc.nist.gov/pubs/sp/800/55/r1/final"
status: "approved"
classification: "public"
audience: "security leadership, GRC, program managers"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
---

# NIST SP 800-55 Rev 1 — Information Security Performance Measurement Template Governance

## Profile

This template governs the design, collection, validation, and reporting cycle for information security performance measures. It applies NIST SP 800-55 Rev 1's three-tier model (implementation, effectiveness/business, impact) so that security programs can demonstrate operational maturity, business alignment, and strategic influence.

## Identifier table

| Field | Value |
| --- | --- |
| Standard | NIST SP 800-55 Rev 1 |
| Title | Performance Measurement Guide for Information Security |
| Publisher | NIST Computer Security Resource Center |
| Topic | Information Security Metrics |
| Governance role | Security measurement programme governance |

## Scope

The template covers the end-to-end lifecycle of a security measure:

- Stakeholder identification and audience segmentation (CISO, board, audit, operations).
- Measure selection against implementation, effectiveness/business, and impact tiers.
- Data source identification, collection automation, and quality controls.
- Target setting, baseline establishment, and threshold tuning.
- Reporting cadence, visualisation standards, and narrative context.
- Retirement criteria when a measure no longer drives decision-making.

## Three-tier measure model

NIST SP 800-55 Rev 1 recommends a layered measurement approach:

- **Implementation measures** — do controls exist and operate as designed (e.g., percentage of laptops with EDR active, MFA enrolment rate).
- **Effectiveness / business measures** — are controls producing the intended effect on the business process (e.g., mean time to detect, phishing simulation click-through decline, patch SLA attainment).
- **Impact measures** — what business outcome has changed (e.g., reduction in regulatory findings, customer churn attributed to security, reduction in material loss events).

The template documents which tier each measure belongs to and the data lineage that supports the conclusion.

## Plan / Inputs

- Current control inventory mapped to NIST SP 800-53 families or ISO/IEC 27001 Annex A controls.
- Stakeholder list with reporting expectations and decision rights.
- Telemetry catalogue listing each candidate measure's source system, owner, and freshness.
- Baseline values and target thresholds.
- Tooling budget and integration plan for collection automation.

## ORCHORDS Profile table

| ORCHORDS field | Guidance |
| --- | --- |
| Measure ID | Stable identifier following the `<domain>-<measure>` convention. |
| Tier | Implementation, effectiveness/business, or impact. |
| Audience | Primary decision-maker consuming the measure. |
| Data source | Authoritative system of record with refresh cadence. |
| Collection method | Automated query, manual attestation, or hybrid. |
| Target and threshold | Numeric goal plus yellow/red escalation thresholds. |
| Action linkage | Action that triggers when the measure breaches threshold. |

## Implementation Notes

- Avoid vanity measures; every metric must support a decision a named stakeholder can take.
- Prefer measures built from existing telemetry before standing up new collection pipelines.
- Pair each metric with a data quality statement describing completeness, accuracy, and timeliness.
- Set targets from external benchmarks, internal baselines, and risk appetite, not from aspirational guesses.
- Rotate the metrics dashboard quarterly so that stale measures retire and high-value measures gain visibility.

## Companion Documents

- NIST SP 800-55 Rev 1 (canonical)
- NIST SP 800-137 (Information Security Continuous Monitoring)
- ISO/IEC 27004 (Information Security Measurement)
- CMU SEI Measures for Managing Operational Resilience
- FAIR (Factor Analysis of Information Risk) taxonomy
