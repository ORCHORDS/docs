---
title: "Churn Early Warning Composite"
owner: "Customer Success Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Churn Early Warning Composite

## Purpose

Establish an accountable, evidence-based approach to combining independent leading indicators into a defensible composite early-warning system for customer churn. The objective is to detect deteriorating customer outcomes early enough to act, without inflating the warning rate through redundant, correlated, or low-quality signals.

## Scope

This policy applies to any composite indicator that combines two or more leading or coincident churn signals (adoption decay, support sentiment, executive-sponsor engagement, value-realisation slippage, contract milestone drift, and similar) into a single early-warning score or decision. It covers automation-driven escalation routing, renewal-risk pipelines, executive review sampling, and any report consumed by customer success leadership. It does not apply to single-signal alerts, which are governed by the signal-validation policy, nor to forecasting models that predict aggregate retention at a population level.

## Requirements

- Every component signal that enters a composite MUST itself satisfy the adoption-signal-validation policy. A composite MUST NOT incorporate a signal that has been quarantined or whose freshness, completeness, or calibration test has failed.
- Component signals MUST be selected for independence. The selection MUST include a written justification that explains why the chosen signals are expected to provide non-overlapping information about churn risk. Two signals that move together through a common cause MUST NOT be treated as independent evidence.
- The combination rule (linear weighting, decision tree, classifier output, or expert rule) MUST be documented with the rationale, the training or calibration period, and the population on which it was tuned. The combination rule MUST NOT be derived from convenience or inherited from a prior model without re-validation.
- The composite MUST be calibrated against ground truth at the documented cadence. Calibration MUST include precision, recall, false-positive rate, lead-time distribution, and the cost of missed detections versus the cost of false alarms. Calibration results MUST be retained.
- Thresholds that gate customer-facing action MUST be reviewed at least every review cycle. Threshold changes MUST be approved by an independent reviewer and staged before promotion; unapproved threshold changes MUST NOT take effect.
- The composite MUST be reproducible. Two independent runs over the same input window and configuration MUST yield the same ranking within a documented tolerance.
- The composite MUST be auditable. From any decision taken on the basis of the composite, an investigator MUST be able to recover the component signals, the combination rule version, the calibration snapshot, and the raw input lineage within the audit-retention window.
- The composite MUST be evaluated for bias across customer sub-populations. If the composite's accuracy varies materially by segment (industry, region, size, deployment model, or other relevant axis), the variation MUST be documented and either corrected or carried as an explicit limitation in any downstream decision.
- Automated actions triggered by the composite MUST be reversible. The action MUST be logged with the composite value, the components that contributed, the threshold crossed, and the recipient of the action.
- The composite MUST include a human-review path. No composite-driven action MAY bypass human judgement where the action affects a customer-visible commitment, a renewal term, or a service-tier change.
- Lead-time claims (for example, "the composite detects churn risk 60 days earlier than the baseline") MUST be backed by a documented evaluation study, not asserted from convenience. The study MUST be retained and re-run when the composite changes.
- The composite MUST degrade gracefully. If one component signal is unavailable or quarantined, the composite MUST either fall back to a documented degraded mode (with the missing components flagged) or withhold its prediction until the signal is restored. Silent fallback to a less-informative score without disclosure is prohibited.
- The composite MUST NOT be used to penalise, reprice, or de-scope a customer without independent human review, regardless of the composite's confidence level.

## Controls

- A back-testing pipeline replays historical data through the composite and produces precision, recall, false-positive rate, and lead-time metrics. The pipeline MUST be re-run at every material change to the combination rule.
- A challenge dataset of confirmed churn and confirmed retained customers is maintained; the composite's predictions on this dataset MUST be reviewed at each calibration cycle.
- A "minimum viable component" rule requires the composite to draw on at least two independent signals; a composite that has degenerated to a single signal MUST be flagged for review and either restored or retired.
- A periodic surprise audit submits named false positives and false negatives from recent periods to the model owner for root-cause analysis. Findings are recorded in a register that informs future calibration.
- A documented change-control procedure governs threshold and combination-rule changes. Each change MUST include an evaluation note, an approval signature, and a deployment plan.

## Canonical sources

- ISO/IEC 27001:2022, Information security management — Requirements: https://www.iso.org/standard/27001
- NIST SP 800-53 Rev. 5, Security and Privacy Controls for Information Systems and Organizations: https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- NIST SP 800-161 Rev. 1, Cybersecurity Supply Chain Risk Management Practices: https://csrc.nist.gov/pubs/sp/800/161/r1/final
- ISO/IEC 42001:2023, Information technology — Artificial intelligence management system: https://www.iso.org/standard/81230.html
- OECD, Guidelines on the Protection of Privacy and Transborder Flows of Personal Data: https://www.oecd.org/digital/privacy-guidelines/
- Customer Success Network, Churn and retention research (public guidance): https://www.customersuccessnetwork.com/
- GainGrowRetain, Churn early-warning methodology (public guidance): https://www.gaingrowretain.com/
- ISO/IEC 5259-4:2024, Data quality — Part 4: Data quality process framework: https://www.iso.org/standard/81090.html