---
title: "Adoption Signal Validation"
owner: "Customer Success Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Adoption Signal Validation

## Purpose

Establish an accountable, evidence-based approach to validating the adoption telemetry that drives customer-success decisions. The objective is to distinguish signal from noise, to detect false positives before they bias human judgement, and to ensure that automation-derived conclusions are calibrated against ground truth before they reach a customer-facing action.

## Scope

This policy applies to any quantitative adoption signal — usage frequency, feature activation, breadth, recency, latency-sensitive interaction counts, integration completion, and similar — that is consumed by customer success automation, executive reviews, health scores, segmentation, or renewal-risk pipelines. It does not apply to free-form qualitative feedback, which is governed by the feedback-loop policy, nor to billing or commercial telemetry.

## Requirements

- Every adoption signal that informs a customer-facing decision MUST have a documented owner, a written operational definition, the source system, the freshness bound, and a documented expected latency.
- Signals MUST be evaluated for freshness on every cycle. A signal older than its documented freshness bound MUST NOT be acted on as if current; it MUST either be regenerated, marked stale, or routed to human review.
- Signals MUST be evaluated for completeness. Where the underlying data pipeline has known coverage gaps (specific environments, anonymised users, offline integrations, partial event delivery), the signal MUST disclose the gap and either impute the missing component transparently or withhold the signal until coverage is restored.
- Signals MUST be evaluated for false-positive risk. A documented false-positive inventory MUST identify events or states that look like adoption but are not — for example, automated test traffic, scripted service-account calls, training sandboxes, partner demonstration tenants, or break-glass administrative sessions. Inventory entries MUST specify the suppression rule and its current effectiveness.
- Signals MUST be calibrated against ground truth at the documented calibration cadence. Calibration MAY use sampled ground-truth labels, customer-confirmed milestones, support-ticket evidence, or external benchmarks. The calibration record MUST be retained alongside the signal definition for at least one full review cycle.
- Signals MUST be unit-tested. The test corpus MUST include at least one case for each known false-positive class, one case for each known coverage gap, and one case for the expected baseline of a healthy customer.
- Signals MUST be reproducible: two independent runs over the same input window and configuration MUST yield the same result within a documented tolerance. Non-deterministic signals MUST carry a confidence interval or qualitative uncertainty.
- Automated actions triggered by a signal MUST be reversible. The action MUST be logged with the triggering signal value, the threshold crossed, the timestamp, and the recipient of the action, and the rollback MUST be exercisable within a documented time bound.
- A signal that fails validation (for example, a freshness violation, a coverage regression, a calibration drift beyond tolerance) MUST be quarantined. No new automated action may be triggered by a quarantined signal; in-flight actions MAY continue under human review but MUST be re-evaluated when the signal is restored.
- Threshold values that gate customer-facing actions MUST be documented with the rationale, the date of last review, and the operational consequences. Threshold changes MUST be approved by an independent reviewer before they take effect.
- Signals MUST be auditable. The lineage from a customer-visible conclusion back to the raw events MUST be recoverable within the audit-retention window. Where lineage cannot be reconstructed, the conclusion MUST be treated as unverified.
- Telemetry that aggregates across distinct user populations (for example, shared accounts, kiosk accounts, service accounts) MUST be evaluated for population-mixing bias before it is reported as adoption. A signal whose composition changes silently between reporting periods MUST be flagged for human review.
- Where adoption telemetry is subject to privacy controls (such as data minimisation, retention limits, or consent restrictions), the signal definition MUST reconcile the analytics requirement with the privacy constraint, and the reconciliation MUST be reviewed by the data-governance function.

## Controls

- A daily freshness probe runs each production signal against a synthetic input and asserts the freshness bound. Failures open an incident.
- A coverage dashboard reports the fraction of the active customer base represented in each signal, the change in coverage versus the prior cycle, and the top reasons for exclusion.
- A calibration store retains labelled ground-truth samples, the calibration metric used (precision, recall, calibration error, or another appropriate measure), and the recertification date.
- A suppression registry tracks every false-positive rule, its scope, and the last test date. Suppression rules that have not been tested within the review cycle are escalated for review.
- A "two-person rule" applies to threshold changes that affect a customer-facing action: the analyst proposing the change and an independent approver MUST both sign off, and the change MUST be staged in a non-production environment before promotion.

## Canonical sources

- ISO/IEC 27001:2022, Information security management — Requirements: https://www.iso.org/standard/27001
- NIST SP 800-53 Rev. 5, Security and Privacy Controls for Information Systems and Organizations: https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- NIST SP 800-161 Rev. 1, Cybersecurity Supply Chain Risk Management Practices: https://csrc.nist.gov/pubs/sp/800/161/r1/final
- ISO/IEC 5259-1:2024, Data quality — Part 1: Overview and concepts: https://www.iso.org/standard/81087.html
- ISO/IEC 25012:2008, Data quality model: https://www.iso.org/standard/35736.html
- OECD, Data quality and statistics: https://www.oecd.org/digital/data-quality/
- Customer Success Network, Validation of CS Metrics (public guidance): https://www.customersuccessnetwork.com/
- TPC Benchmark standards (publicly published methodology norms): https://www.tpc.org/