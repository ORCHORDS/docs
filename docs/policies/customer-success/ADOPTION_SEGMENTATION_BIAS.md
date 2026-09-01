---
title: "Adoption Segmentation Bias"
owner: "Customer Success Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Adoption Segmentation Bias

## Purpose

Establish an accountable, evidence-based approach to identifying, measuring, and preventing bias when customer populations are sliced by adoption behaviour. The objective is to ensure that segmentation decisions produce fair service outcomes and defensible conclusions, rather than entrenching historical inequalities or arbitrary thresholds that disadvantage certain customer groups.

## Scope

This policy applies to any customer-success segmentation that uses adoption telemetry — including usage frequency, depth, breadth, recency, and feature-level activation — as a primary or supporting criterion. It covers internal cohorts used for service prioritisation, success-plan scoping, intervention routing, executive review sampling, and renewal-risk tiering. It does not cover commercial segmentation that is exclusively price- or revenue-driven (such segmentation is governed by commercial policy), nor does it cover security- or privacy-driven access tiers.

## Requirements

- Segmentation rules that depend on adoption telemetry MUST document the data source, the calculation window, the inclusion and exclusion filters, and the operational definition of each adoption variable.
- Segment definitions MUST be reviewed at least once per review cycle by an owner who is independent of the team that consumes the segment, and the review MUST consider whether the segmentation produces unfair or ineffective service outcomes for any protected, vulnerable, or structurally disadvantaged customer group.
- Segmentation inputs MUST be tested for selection bias. Where the telemetry pipeline systematically under-counts customers in a specific environment (for example, customers using assistive technology, customers operating through restricted networks, or customers with intermittent connectivity), the segment definition MUST either adjust for that under-count or carry a documented limitation note.
- Cut-off thresholds (for example, "fewer than three active users in 30 days classifies a customer as low-adoption") MUST be derived from a transparent method: a documented distribution analysis, a calibration against ground-truth outcomes, or an external benchmark — not from convenience or from inherited defaults.
- Segmentation MUST NOT be used as a covert mechanism to deprioritise, deny, or delay service to a customer or customer group. Where segmentation drives service-tier differentiation, the differentiated service MUST be justified by a documented service-level outcome and disclosed to the customer in plain language.
- Adoption signals that depend on user identifiers, role assignments, or authentication state MUST be evaluated for proxy bias: an apparent "low-adoption" reading that reflects an administrative artefact (for example, an unmapped role or a missing licence assignment) MUST NOT be treated as evidence of customer disengagement without corroboration.
- Reports that quote segment-level statistics MUST disclose the segment size, the confidence interval or qualitative uncertainty, and the date of the underlying snapshot. Reporting MUST NOT aggregate segments in ways that mask small-sample variance.
- A customer or customer advocate who disputes their segment assignment MUST have a documented escalation path that is reviewed by a second pair of eyes and resolved within an explicit time bound.
- Segmentation logic MUST be version-controlled. Any change to a definition MUST include a migration note that describes accounts whose segment changes as a consequence, and the change MUST be approved before it affects customer-facing decisions.
- The function MUST maintain a register of known biases, mitigations in place, and residual risks. The register MUST be reviewed at every policy recertification.
- Segments derived from automated models (such as k-means clusters or classifier outputs) MUST be explainable to a non-technical reviewer. Black-box segments whose composition cannot be summarised in plain language MUST NOT be used as the sole basis for a customer-facing decision.

## Controls

- A quarterly bias audit compares segment-level outcomes (service response time, intervention reach, escalation rate, renewal-risk score) against an unsegmented baseline and against a counterfactual segment produced by an independent method. Material divergences are investigated and either resolved or documented.
- A "minimum viable sample" rule prevents the function from acting on segment-level conclusions drawn from a population below a documented size threshold without explicit human review.
- The function maintains a redacted examples library that catalogues historical biases detected, the remediation applied, and the lesson captured, so that new segmentation work can reference past mitigations.
- Any segmentation model that drives a downstream automated decision MUST have a documented holdout set used for periodic fairness testing. The test results MUST be retained with the model documentation.
- Where a regulatory or contractual obligation prohibits certain segmentations (for example, those that would amount to discriminatory service under consumer-protection law), the function MUST implement a hard block in the segmentation pipeline and verify it by independent test before each release.

## Canonical sources

- ISO/IEC 27001:2022, Information security management — Requirements: https://www.iso.org/standard/27001
- NIST SP 800-53 Rev. 5, Security and Privacy Controls for Information Systems and Organizations: https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- ISO/IEC 20547-3:2020, Big data reference architecture — Part 3: Reference architecture: https://www.iso.org/standard/73603.html
- OECD, Principles for the Governance of Data and Statistics (public summary): https://www.oecd.org/digital/data-governance/
- Customer Success Metrics Standards — GainGrowRetain / Customer Success Network (public guidance): https://www.gaingrowretain.com/
- NIST SP 800-66 Rev. 2, Implementing the HIPAA Security Rule: https://csrc.nist.gov/pubs/sp/800/66/r2/final
- ISO/IEC 42001:2023, Information technology — Artificial intelligence management system: https://www.iso.org/standard/81230.html