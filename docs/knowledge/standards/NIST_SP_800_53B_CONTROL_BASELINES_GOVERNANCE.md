# NIST SP 800-53B Control Baselines Governance

## Purpose

NIST SP 800-53B provides control baselines that serve as a starting point for tailoring SP 800-53 controls to specific information systems and organizations. The standard defines three baselines (LOW, MODERATE, HIGH) and supplies overlay guidance. Governance ensures that the chosen baseline reflects the system's impact level, that tailoring is documented, and that overlays are applied where mission-specific needs justify them.

## Current context and source status

NIST SP 800-53B was published alongside SP 800-53 revision 5. The current revision of SP 800-53 (Rev. 5) and 800-53B are part of the Joint Task Force Interagency Working Group publications. Verify the current revision status before treating any control identifier or baseline as a current requirement.

## Governance workflow and controls

### 1. Determine the system impact level

Categorize the system using FIPS 199 (security objectives) and FIPS 200 (minimum security requirements). Document the impact level: LOW, MODERATE, or HIGH.

### 2. Select the baseline

Select the baseline (LOW, MODERATE, or HIGH) that corresponds to the system's impact level. The baseline provides the initial set of controls.

### 3. Apply tailoring

Apply tailoring per SP 800-53B guidance:

- scoping considerations (apply to physical, logical, or both);
- selection (include or exclude a control);
- parameterization (assign values to control parameters);
- supplementation (add controls not in the baseline).

Document the tailoring decisions and the rationale.

### 4. Apply overlays

Apply overlays where mission-specific needs justify deviation from the baseline. Common overlays include Privacy Overlay (SP 800-53A), National Security Overlay (SP 800-53B), and sector-specific overlays (for example, healthcare, financial services).

### 5. Document the baseline and tailoring

Document the selected controls, the tailoring decisions, and the overlays. Maintain a System Security Plan (SP 800-18) that reflects the result.

### 6. Review and update

Review the baseline and tailoring when context changes, when SP 800-53 is updated, or when overlays change. Track changes.

### 7. Use baselines in assessment

Use the baseline and tailoring as the basis for assessment (SP 800-53A). Identify deviations and document justifications.

## Validation and evidence

- System categorization (FIPS 199, FIPS 200).
- Selected baseline and version.
- Tailoring decisions with rationale.
- Overlays applied with rationale.
- System Security Plan.
- Assessment report.

## Failure correction

Common defects include incorrect impact level selection, tailoring without rationale, and missing overlay application. Corrective actions include an impact-level review, a tailoring-rationale completeness check, and an overlay coverage matrix.

## Limitations

- NIST SP 800-53B is specific to U.S. federal information systems; other jurisdictions have analogous frameworks.
- The standard does not cover national security systems in full; refer to SP 800-53B for national security overlays.
- Tailoring requires judgement; over-tailoring can weaken security.
- Baselines evolve with revisions of SP 800-53.

## Canonical sources

- NIST SP 800-53B, Control Baselines for Information Systems and Organizations, current revision.
- NIST SP 800-53, Security and Privacy Controls for Information Systems and Organizations, current revision.
- NIST SP 800-18, Guide for Developing Security Plans for Federal Information Systems, current revision.
- FIPS 199, Standards for Security Categorization of Federal Information and Information Systems.
- FIPS 200, Minimum Security Requirements for Federal Information and Information Systems.

## Scope note

This article belongs to the standards leaf and cross-references the security leaf for control selection, the engineering leaf for system categorization, and the business leaf for risk acceptance.
