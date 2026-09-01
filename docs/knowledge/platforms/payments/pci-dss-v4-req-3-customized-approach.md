# PCI DSS v4 Requirement 3 Customized Approach

**Issue:** PCI DSS v4 introduced the Customized Approach as a defined alternative to the Prescribed Approach for satisfying security requirements. Under the Customized Approach, the entity designs its own control that meets the requirement's stated Customized Approach Objective, then validates it through a Targeted Risk Analysis (TRA) and continuous testing. The Customized Approach is not an exemption; it is a structured way to demonstrate that an alternative control meets the requirement's intent. Requirement 3 (Protect Stored Account Data) is among the most common candidates because the Prescribed Approach requires specific technical implementations (truncation, hashing, encryption) that may not match every architecture. Engineering a Customized Approach for Requirement 3 means understanding the Customized Approach Objective, designing controls that meet it, documenting the TRA, and operating the continuous testing program that the v4 standard requires.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Customized Approach Objective

1. **The objective is the constraint.** Each PCI DSS v4 requirement has a Customized Approach Objective statement that defines what the requirement is intended to protect. For Requirement 3, the objectives span: account data is not stored after authorization except where defined as allowable, sensitive authentication data (SAD) is not stored after authorization, stored account data is rendered unreadable, account data is protected against unauthorized access, and cryptographic material is managed.
2. **The control design must meet the objective, not the literal requirement.** A Customized Approach that achieves the objective through a tokenization architecture is acceptable; a Customized Approach that stores PAN in a poorly-controlled spreadsheet is not. The QSA evaluates whether the control meets the objective, not whether the literal Prescribed Approach was followed.
3. **The entity owns the design and the evidence.** Unlike the Prescribed Approach where the QSAC reviews the implementation against defined tests, the Customized Approach requires the entity to design and operate the control, document the TRA, and produce evidence that meets the objective. The QSA reviews the design and the evidence, not the implementation itself.

## Designing a Requirement 3 Customized Approach

1. **Identify the requirement sub-clauses covered.** Requirement 3 has multiple sub-requirements (3.1 through 3.7 in v4, with additional sub-requirements for issuers and acquirers). A single Customized Approach may cover multiple sub-requirements, but each must be addressed individually in the TRA.
2. **Map the control to each objective statement.** For each objective statement, the control design must be evaluated against the objective. A tokenization-only architecture does not address SAD retention control (which is about preventing storage altogether) — the entity must additionally operate a SAD-non-retention policy.
3. **Specify the testing cadence.** PCI DSS v4 requires Customized Approach controls to be tested on a defined cadence (at minimum annually, often more frequently) by an independent function. The TRA must specify the cadence and the testing methodology.

## Targeted Risk Analysis

1. **Mandatory TRA for each Customized Approach.** PCI DSS v4 requires a TRA document for each Customized Approach, with the analysis documenting the threat, the control, the residual risk, and the operating effectiveness measures.
2. **TRA components.** The TRA must include: the requirement being met via Customized Approach, the stated objective, the proposed control, the threat model, the residual risk, the operating effectiveness metrics, and the testing plan. The TRA is reviewed by the QSA at each assessment.
3. **TRA retention.** The TRA must be retained for at least three years after the Customized Approach control is in place, and updated when the threat model or the control changes. Engineering must version the TRA document and review it on a defined cadence.

## Operational obligations

1. **Continuous monitoring.** The Customized Approach control must be continuously monitored; the metrics must be captured and reported to the security function on a defined cadence. A monitoring gap is a compliance breach.
2. **Annual testing by an independent function.** PCI DSS v4 requires Customized Approach controls to be tested at least annually by an independent function (typically internal audit or a third-party assessor) against the control's effectiveness criteria. The test results are reviewed at each assessment.
3. **Change management.** Any change to the Customized Approach control triggers a TRA update and a QSA notification. Engineering must treat Customized Approach controls as regulated components subject to formal change control.

## Engineering controls

1. **Control catalog.** Maintain a catalog of Customized Approach controls, each linked to the requirement, the objective, the TRA, the control implementation, and the testing plan. The catalog must be versioned and reviewable.
2. **Effectiveness metrics.** For each Customized Approach, define and capture the effectiveness metric: the measurement that proves the control is operating as designed. A tokenization Customized Approach for Requirement 3 might measure the share of PAN references that are tokens rather than plaintext.
3. **Audit trail.** The Customized Approach requires evidence that the control operated as designed throughout the audit period. Engineering must produce this evidence on demand, including the control operating logs, the effectiveness metric time series, and the TRA review history.

## Failure modes

1. **Customized Approach as exemption.** Treating the Customized Approach as a way to bypass the Prescribed Approach without meeting the objective is a structural compliance failure. The QSA evaluates the objective, not the literal control.
2. **Stale TRA.** A TRA written at Customized Approach design time and never updated as the threat model evolves loses its validity. The TRA is a living document, not a one-time submission.
3. **Testing gaps.** Customized Approach controls that are not tested at the documented cadence are out of compliance. Engineering must enforce the testing cadence with calendar controls and the testing function must produce evidence on each cycle.

## Canonical sources

1. PCI Security Standards Council, Payment Card Industry Data Security Standard, Version 4.0, including the Customized Approach objectives appendix and the Targeted Risk Analysis template. https://www.pcisecuritystandards.org/document_library
2. PCI Security Standards Council, Customized Approach Template and TRA Guidance, v4 supporting documentation. https://www.pcisecuritystandards.org/document_library
