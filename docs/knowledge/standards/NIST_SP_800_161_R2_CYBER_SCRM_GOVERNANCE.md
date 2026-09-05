# NIST SP 800-161 Rev. 2 Cyber Supply Chain Risk Management Governance

## Purpose

NIST SP 800-161 Rev. 2 (May 2022) provides guidance on cybersecurity supply chain risk management (C-SCRM). Governance ensures that ORCHORDS identifies, assesses, mitigates, and monitors supply chain risks across the supplier, acquirer, and integrator roles, and that the SCRM controls are integrated with the broader enterprise risk function.

## Current context and source status

SP 800-161 Rev. 2 supersedes Rev. 1 (2018) and aligns with executive order 14028. The publication is the canonical reference for C-SCRM controls and overlays. Verify current revision status before treating specific control lists as authoritative.

## Governance workflow and controls

### 1. Establish the SCRM program

- Define the C-SCRM strategy, policy, and governance structure.
- Assign roles and responsibilities across enterprise risk, procurement, engineering, and security.
- Establish integration with enterprise risk management and with the system development lifecycle.

### 2. Identify and prioritize suppliers and components

- Maintain a supplier inventory with criticality and dependency mapping.
- Maintain a software and hardware component inventory with provenance and integrity records.
- Prioritize based on criticality, exposure, and threat intelligence.

### 3. Assess supplier risk

- Conduct supplier assessments using a documented questionnaire and evidence-based review.
- Require SBOMs for software suppliers and integrity attestations for hardware suppliers.
- Validate compliance with contractual security requirements.

### 4. Mitigate supply chain risks

- Apply controls from SP 800-161 Appendix A and overlays tailored to criticality.
- Require verified provenance, code signing, and attestation for software components.
- Diversify suppliers where feasible; document single points of failure.

### 5. Monitor and respond

- Monitor suppliers for changes in posture, advisories, and breach disclosures.
- Require notification of incidents within contractual SLAs.
- Feed findings into enterprise risk reporting and into the engineering lifecycle.

## Validation and evidence

- C-SCRM strategy, policy, and governance records.
- Supplier and component inventory with criticality.
- Supplier assessments and contractual security records.
- SBOMs and integrity attestations.
- Incident notifications and post-incident reviews.

## Failure correction

Common defects include incomplete supplier inventory, missing SBOM requirements, and weak contractual notification clauses. Corrective actions include inventory completeness review, SBOM enforcement check, and contractual clause alignment review.

## Companion documents

- NIST_SP_800_218_SSDF_GOVERNANCE.md
- ISO_IEC_27001_2022_VERSION_TRANSITION_GOVERNANCE.md
- NIST_SP_800_53B_CONTROL_BASELINES_GOVERNANCE.md
