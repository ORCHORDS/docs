# NIST SP 800-37 Rev. 3 Risk Management Framework Governance

## Purpose

NIST SP 800-37 Rev. 3 (December 2018) describes the Risk Management Framework (RMF) for information systems and organizations. The RMF provides a disciplined, structured, and flexible process for managing security and privacy risk. Governance ensures that ORCHORDS applies all seven RMF steps consistently, that the selected control baselines align with system impact, and that the continuous monitoring step drives ongoing authorization decisions.

## Current context and source status

SP 800-37 Rev. 3 supersedes Rev. 2 (2014) and aligns with the next-generation RMF including the Prepare step. Rev. 3 incorporates privacy into the same structure as security. Verify the current revision status before treating specific step definitions as authoritative.

## Governance workflow and controls

### 1. Prepare

- Assign roles and responsibilities for RMF execution.
- Establish a risk management strategy and tolerance.
- Identify common controls and the organization-wide risk assessment.

### 2. Categorize

- Categorize the system and the information processed using FIPS 199 and FIPS 200.
- Document the security and privacy categorizations with rationale.

### 3. Select

- Select the SP 800-53 control baseline aligned with the categorization.
- Apply tailoring and overlays per SP 800-53B.
- Document selected controls in the System Security and Privacy Plan (SSPP).

### 4. Implement

- Implement the selected controls and document the implementation in the SSPP.
- Track deployment of common controls to the system owner.

### 5. Assess

- Assess controls using the procedures in SP 800-53A.
- Produce an assessment report with findings and recommendations.
- Track remediation of assessment findings.

### 6. Authorize

- Prepare the Plan of Action and Milestones for residual findings.
- Authorize the system based on the SSPP, assessment report, and POA&M.
- Document the authorization decision and conditions.

### 7. Monitor

- Monitor controls on a documented cadence with continuous monitoring strategy.
- Update the SSPP, assessment report, and POA&M on changes.
- Trigger re-authorization when risk profile changes significantly.

## Validation and evidence

- System categorization with rationale.
- Selected baseline, tailoring decisions, and overlays.
- SSPP, assessment report, and POA&M.
- Authorization decision letter and conditions.
- Continuous monitoring strategy and records.

## Failure correction

Common defects include missing Prepare step outputs, weak continuous monitoring, and stale authorization decisions. Corrective actions include Prepare step completeness review, monitoring cadence audit, and authorization freshness check.

## Companion documents

- NIST_SP_800_53B_CONTROL_BASELINES_GOVERNANCE.md
- NIST_SP_800_30_R1_RISK_ASSESSMENT_GOVERNANCE.md
- ISO_IEC_27001_2022_VERSION_TRANSITION_GOVERNANCE.md
