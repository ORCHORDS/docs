# PCI DSS v4 Customized Approach Targeted Analysis

**Issue:** The Targeted Risk Analysis (TRA) is the mandatory document that PCI DSS v4 requires for every Customized Approach control, and for specific requirement sub-clauses where the standard allows frequency or timing variations. The TRA is not a generic risk assessment; it is a structured analysis with required components — threat model, control design, residual risk, operating effectiveness metrics, testing plan, and review cadence — that demonstrate the entity's Customized Approach meets the requirement's stated objective. Engineering and security teams that produce shallow TRAs fail at QSA review and find themselves reverting to the Prescribed Approach at assessment time. A TRA is a regulated artifact with retention and update obligations; treating it as a one-time document is a structural compliance failure.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## TRA scope

1. **Customized Approach TRAs.** Every Customized Approach control requires a TRA. A merchant with three Customized Approach controls has three TRAs, each linked to the requirement and the objective statement. The TRAs are reviewed by the QSA at each assessment and form part of the Report on Compliance (ROC) or Self-Assessment Questionnaire (SAQ) supporting documentation.
2. **Frequency-variation TRAs.** Certain PCI DSS v4 sub-requirements allow the entity to define its own cadence for activities that the Prescribed Approach specifies at a fixed cadence (e.g., certain log review frequencies, certain vulnerability scan frequencies). Each frequency variation requires a TRA that justifies the chosen cadence against the threat model.
3. **TRA scope is narrow.** A TRA covers one control or one frequency variation. A combined TRA covering multiple controls is not acceptable; the QSAC evaluates each control individually against its objective.

## Required TRA components

1. **Threat model.** The TRA must document the threat: who might attack the control, what assets are at risk, what attack vectors are realistic, and what the impact of a successful attack would be. The threat model anchors the residual-risk analysis.
2. **Control design.** The TRA must describe the proposed control: what it does, how it operates, where in the architecture it sits, who owns it, and how it produces evidence of effectiveness. The control design must be specific, not generic — a control that "monitors access" is not a control design.
3. **Residual risk.** The TRA must analyze the residual risk after the control is applied. Where the residual risk is non-zero, the TRA must describe compensating factors or accepted risk, and the entity's executive sponsor must sign off on the acceptance.
4. **Operating effectiveness metrics.** The TRA must define the metrics that prove the control is operating as designed. The metrics are captured continuously and reviewed at the defined testing cadence.
5. **Testing plan.** The TRA must specify how the control is tested: who tests it, on what cadence, against what criteria, and what the pass/fail threshold is. PCI DSS v4 requires Customized Approach testing at least annually, with the QSAC reviewing the test results.

## TRA authoring

1. **Cross-functional authoring.** A TRA is not solely the security team's product. Engineering, security, operations, and the control owner must each contribute: engineering for the control design and effectiveness metrics, security for the threat model and residual risk, operations for the testing plan, the control owner for sign-off.
2. **Threat-model discipline.** The threat model must be specific: "an external attacker exfiltrates PAN from the legacy CRM database" is a threat; "security incidents" is not. The QSAC evaluates whether the threat model is realistic and complete.
3. **Evidence specificity.** The operating effectiveness metrics must be measurable: "the share of PAN references in the production database that are tokens rather than plaintext, sampled daily" is a metric; "the tokenization system is operating" is not.

## TRA review and update

1. **Annual review.** PCI DSS v4 requires the TRA to be reviewed at least annually. The review produces updated threat models, refreshed residual-risk analysis, and confirmation that the control is still meeting the objective.
2. **Change-triggered update.** Any material change to the control, the threat model, the operating environment, or the entity's risk appetite triggers a TRA update. The QSAC expects a TRA that reflects the current state, not the original authoring.
3. **QSA-observed findings.** If the QSA identifies a gap in a TRA at assessment, the entity must update the TRA and the control. A TRA with an open QSA finding is not in compliance.

## Engineering controls

1. **TRA template and tooling.** Engineering should adopt the PCI SSC's TRA template as the structural baseline and customize it for the entity. A TRA authoring tool that enforces the required components reduces the risk of incomplete submissions.
2. **TRA repository.** TRAs are retained for at least three years (per PCI SSC guidance and v4 supporting documentation) and must be retrievable for assessment. A versioned repository with the current TRA, the prior TRAs, and the review history is the minimum operational control.
3. **Metric capture pipeline.** The TRA's effectiveness metrics must be captured automatically and stored for review. A metric defined in the TRA but captured manually or in an ad-hoc spreadsheet fails the QSAC's evidence test.

## Failure modes

1. **TRA written for the QSA, not for the threat.** A TRA that mirrors PCI SSC template language without specific threat models or control designs passes form but fails substance. The QSA evaluates whether the TRA reflects the actual control and the actual threat.
2. **Effectiveness metrics that do not measure effectiveness.** Metrics that are easy to capture (system uptime, log volume) are not effectiveness metrics. The metric must measure whether the control achieves the objective, not whether the control is running.
3. **TRA orphaned from control.** A TRA that describes a control that is not actually implemented, or an implementation that has drifted from the TRA's description, is a structural failure. The TRA must be reviewed whenever the control changes, and the control must be reviewed whenever the TRA changes.

## Canonical sources

1. PCI Security Standards Council, Payment Card Industry Data Security Standard, Version 4.0, Section "Targeted Risk Analyses" and the Customized Approach Appendix. https://www.pcisecuritystandards.org/document_library
2. PCI Security Standards Council, "Customized Approach Template" published in the PCI SSC Document Library. https://www.pcisecuritystandards.org/document_library
