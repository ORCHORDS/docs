# NIST SP 800-218 Secure Software Development Framework Governance

## Purpose

NIST SP 800-218 (Version 1.1, February 2022) describes the Secure Software Development Framework (SSDF) with practices for producing well-secured software. Governance ensures that the four SSDF practice families — Prepare the Organization, Protect the Software, Produce Well-Secured Software, and Respond to Vulnerabilities — are applied across the ORCHORDS software lifecycle, with evidence captured for each practice.

## Current context and source status

SP 800-218 v1.1 aligns SSDF with executive order 14028 requirements and is referenced from SP 800-53 Rev. 5 control SA-15. Treat the practice statements as normative; verify the current revision status before adopting a new revision.

## Governance workflow and controls

### 1. Prepare the Organization

- Define security requirements for software development and make them visible to every team.
- Define roles and responsibilities for secure development, including security champions and incident responders.
- Implement supporting toolchains and environments with documented security baselines.

### 2. Protect the Software

- Protect all forms of code from unauthorized access and tampering.
- Provide a documented mechanism for verifying software release integrity.
- Archive and protect each software release with provenance metadata.

### 3. Produce Well-Secured Software

- Design software to meet security requirements and mitigate risks.
- Restrict access to the build and test environments.
- Use proven techniques such as threat modeling, secure coding standards, and code review.
- Configure compilation, interpreter, and build options to improve security.
- Review and analyze human-written code; review and analyze third-party code.
- Test executable code to identify vulnerabilities and verify compliance.

### 4. Respond to Vulnerabilities

- Identify and confirm vulnerabilities on a documented cadence.
- Assess, prioritize, and remediate vulnerabilities within documented SLAs.
- Analyze root cause and feed findings back into the practice families.

## Validation and evidence

- Documented security requirements.
- Toolchain inventory with security baselines.
- Release archive with provenance and integrity verification records.
- Threat model, secure coding standard, and code review evidence.
- Test results and vulnerability management records.
- Root cause analyses linked to practice family updates.

## Failure correction

Common defects include ad hoc security requirements, lack of toolchain baseline, and missing root cause analysis on recurring findings. Corrective actions include a security requirements completeness review, a toolchain baseline audit, and a root cause backlog review.

## Companion documents

- NIST_SP_800_53B_CONTROL_BASELINES_GOVERNANCE.md
- ISO_IEC_27001_2022_VERSION_TRANSITION_GOVERNANCE.md
- NIST_SP_800_161_R2_CYBER_SCRM_GOVERNANCE.md
