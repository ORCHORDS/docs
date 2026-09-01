---
title: "Customer Outcome Regression"
owner: "Customer Success Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Customer Outcome Regression

## Purpose

Establish an accountable, evidence-based approach to detecting, attributing, and responding to a customer-outcome regression — a measurable decline in the outcomes a customer previously attained. The objective is to ensure regressions are surfaced early, attributed honestly, communicated clearly, and resolved through a documented path that leaves the customer outcome at least as well-understood as it was before the regression began.

## Scope

This policy applies whenever an outcome metric tracked in the success plan or value-realisation evidence moves below its documented baseline by a documented threshold, or whenever qualitative signals from the customer, the support organisation, or product telemetry suggest a comparable regression. It covers outcome metrics related to adoption, value realisation, satisfaction, operational reliability, and business impact. It does not cover short-lived fluctuations that do not cross the documented regression threshold, which remain routine operational monitoring.

## Requirements

- A regression MUST be characterised by the metric affected, the direction and magnitude of the change, the time window over which the change occurred, the documented baseline against which it is measured, and the threshold that defines the regression.
- Regression characterisation MUST distinguish sustained regression (the metric remains below baseline across multiple observations) from transient deviation (a single observation that returns to baseline). The two MUST be handled by different response paths.
- Regression attribution MUST be attempted before remediation begins. The attribution MUST consider customer-side causes, product-side causes, integration-side causes, third-party-side causes, and ambiguous causes where multiple contributors are plausible.
- Attribution MUST NOT be concluded prematurely. Where evidence is incomplete, the response MUST proceed in parallel with continued investigation rather than wait for a definitive cause.
- Customer communication MUST occur within the documented time bound for the severity tier. The communication MUST acknowledge the regression, describe the evidence observed, name the investigation owner, and state the expected next contact.
- Customer communication MUST NOT over-promise. Speculative timelines, root-cause statements that have not been validated, or commitments to outcomes that are outside the customer-success function's control MUST NOT be made.
- Internal escalation MUST follow the documented escalation path. Severity tiers MUST be defined in advance; ad-hoc reclassification of severity MUST be approved by an independent reviewer.
- The response plan MUST identify the remediation owner, the actions to be taken, the dependencies, the time bound, and the criteria for closure.
- Regression data MUST be captured in a structured form. The capture MUST include the metrics, the timeline, the attribution, the customer communications, the actions taken, and the closure record. The capture MUST be retained for the audit-retention window.
- Regression closure MUST be evidenced. Closure MUST require that the affected metric has returned to or exceeded baseline for a documented observation period, that the customer has been informed, and that any residual issues have a documented owner.
- A regression that recurs within the documented window after closure MUST trigger a deeper review. The deeper review MUST consider whether the closure was premature, whether the underlying cause was correctly identified, and whether additional controls are required.
- Regression evidence MUST inform the success-plan baseline. Where the metric was previously reliable but has proven volatile, the baseline MAY be re-set, but the re-set MUST be justified, documented, and approved.
- Regression that is traced to a customer-side cause MUST be communicated with care. The communication MUST distinguish observation from judgement and MUST invite the customer to participate in identifying the cause, not assign blame unilaterally.
- Regression that is traced to a product-side cause MUST be routed to the product organisation through the feedback-loop policy. The product acknowledgement MUST be captured.
- Regression evidence MUST NOT be used to penalise the customer, re-price the engagement, or de-scope service without independent human review.
- Regression that involves security, privacy, or compliance implications MUST be reported through the appropriate incident process in parallel with the customer-success response.

## Workflow

1. The detection system or human observer identifies a metric crossing the documented regression threshold.
2. The customer-success lead characterises the regression: metric, magnitude, baseline, threshold, time window.
3. Attribution is initiated, considering customer, product, integration, third-party, and ambiguous categories.
4. The customer is informed within the documented time bound for the severity tier, using language that is honest, evidence-based, and free of speculation.
5. Internal escalation follows the documented path; severity tiers are applied and reviewed.
6. The remediation plan is agreed, with named owners, actions, dependencies, time bound, and closure criteria.
7. Closure is recorded only when the closure criteria are met, including customer acknowledgement.
8. The regression record is reviewed at the documented cadence to surface patterns, calibrate thresholds, and inform future baseline decisions.

## Canonical sources

- ISO/IEC 27001:2022, Information security management — Requirements: https://www.iso.org/standard/27001
- ISO 9001:2015, Quality management systems — Requirements: https://www.iso.org/standard/62085.html
- NIST SP 800-53 Rev. 5, Security and Privacy Controls for Information Systems and Organizations: https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- ITIL 4 Foundation (Axelos public summary): https://www.axelos.com/certifications/itil-service-management/itil-4-foundation
- ISO/IEC 20000-1:2018, Information technology — Service management: https://www.iso.org/standard/70636.html
- OECD, Good governance for critical infrastructure resilience: https://www.oecd.org/governance/risk-management/good-governance-for-critical-infrastructure-resilience/
- Customer Success Network, Outcome regression practice (public guidance): https://www.customersuccessnetwork.com/
- ISO/IEC 27035-1:2024, Information security incident management — Part 1: Principles and process: https://www.iso.org/standard/78973.html