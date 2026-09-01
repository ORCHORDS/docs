---
title: "Technical Health Scorecard"
owner: "Customer Success Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Technical Health Scorecard

## Purpose

Establish an accountable, evidence-based approach to designing a technical-health scorecard — the composite indicator that summarises the technical posture of a customer's deployment. The objective is to ensure the scorecard is defensible, transparent, and useful: signal selection is justified, weighting is documented, calibration is grounded in evidence, and the scorecard's role in customer-facing decisions is bounded by human review.

## Scope

This policy applies to any technical-health scorecard that aggregates signals about the technical state of a customer deployment — including reliability, integration integrity, configuration drift, security configuration, performance, capacity headroom, and upgrade currency. It covers scorecards used for renewal risk, expansion readiness, support-tier assignment, executive reporting, and proactive outreach. It does not apply to ad-hoc technical-status snapshots used for one-time triage.

## Requirements

- A technical-health scorecard MUST document its purpose, the decisions it informs, the decisions it does NOT inform, and the population to which it applies. The scorecard MUST NOT be used for a purpose outside its documented scope without re-approval.
- Each signal in the scorecard MUST satisfy the adoption-signal-validation policy: documented owner, freshness bound, completeness expectation, false-positive inventory, and calibration record. Signals that fail validation MUST NOT contribute to the scorecard until they are restored.
- Signals MUST be selected for relevance, not for convenience. The selection MUST include a written justification for each signal, the failure mode it captures, the data class it depends on, and the expected relationship to the technical posture of interest.
- Weighting MUST be derived from a documented method: expert judgement with named reviewers, an empirical study against ground truth, a calibration against outcome metrics, or an external benchmark. The weighting MUST be re-evaluated at least once per review cycle.
- Weighting changes MUST be approved before they take effect. Unapproved weighting changes MUST NOT influence customer-facing decisions.
- The scorecard MUST be reproducible. Two independent runs over the same input window and configuration MUST yield the same result within a documented tolerance. Non-deterministic scoring MUST carry a confidence interval or qualitative uncertainty.
- The scorecard MUST be calibrated against ground truth at the documented cadence. Calibration MUST consider precision, recall, calibration error, and the cost of false positives versus false negatives. Calibration results MUST be retained.
- The scorecard MUST distinguish a low score caused by a real technical issue from a low score caused by a data-quality issue (for example, a missing telemetry source, an unmapped configuration). Data-quality issues MUST be flagged separately from technical issues; conflating them is prohibited.
- The scorecard MUST include a missing-data behaviour. Where one or more signals are unavailable, the scorecard MUST either fall back to a documented degraded mode (with the missing signals flagged) or withhold the score until the signals are restored.
- The scorecard MUST be evaluated for bias across customer sub-populations. Variations in accuracy by sub-population MUST be investigated and either explained, mitigated, or carried as a documented limitation.
- The scorecard MUST be auditable. From any score produced for a customer, an auditor MUST be able to retrieve the component signals, the weighting, the calibration snapshot, the freshness bound, and the raw input lineage within the audit-retention window.
- The scorecard MUST NOT be used as the sole basis for a customer-facing penalty, a de-scoping, a re-pricing, or a service-tier change. Such decisions MUST be subject to independent human review, with the scorecard as one input among several.
- The scorecard MUST NOT be used to penalise customers whose environments are technically constrained for reasons outside their control (for example, regulated industries, air-gapped deployments, or older operating systems that are themselves within vendor support). The scorecard MUST distinguish between a constrained environment and a poorly-managed one.
- The scorecard MUST be tested before each material change. Tests MUST include a positive case (a healthy deployment scores above the documented threshold), a negative case (a degraded deployment scores below), and a data-quality case (a missing signal produces the documented degraded behaviour).
- The scorecard MUST be transparent to the customer on request. A customer who asks how their score was computed MUST be given a non-confidential summary, identifying the dimensions considered, the signals that contributed, and the recertification cadence.

## Controls

- A signal inventory records every signal, its source, its freshness bound, its last validation date, and its last calibration date.
- A weighting change-control procedure requires an approval signature, an evaluation note, and a staged deployment.
- A calibration store retains labelled ground-truth samples and the calibration metric used.
- A back-testing pipeline replays the scorecard against historical data and produces precision, recall, and calibration error metrics.
- A surprise audit submits named false positives and false negatives to the model owner for root-cause analysis; findings are recorded in a register that informs future calibration.

## Canonical sources

- ISO/IEC 27001:2022, Information security management — Requirements: https://www.iso.org/standard/27001
- NIST SP 800-53 Rev. 5, Security and Privacy Controls for Information Systems and Organizations: https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- ISO/IEC 27002:2022, Information security, cybersecurity and privacy protection — Information security controls: https://www.iso.org/standard/75652.html
- NIST SP 800-55 Rev. 1, Performance Measurement Guide for Information Security: https://csrc.nist.gov/pubs/sp/800/55/r1/final
- ISO/IEC 20000-1:2018, Information technology — Service management: https://www.iso.org/standard/70636.html
- ITIL 4 Foundation (Axelos public summary): https://www.axelos.com/certifications/itil-service-management/itil-4-foundation
- Customer Success Network, Technical health scorecard practice (public guidance): https://www.customersuccessnetwork.com/
- ISO/IEC 42001:2023, Information technology — Artificial intelligence management system: https://www.iso.org/standard/81230.html