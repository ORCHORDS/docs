# NIST SP 800-53B Control Baselines and Overlays Governance

## Purpose

Govern the application of NIST SP 800-53B (Control Baselines for Information Systems and Organizations, September 2020) so that baseline selection — low, moderate, or high impact — is deliberate, overlays are applied through the defined tailoring process, and the resulting control set is documented as the system's authoritative baseline.

## Scope

Applies to baseline selection and tailoring for every system the studio documents under the SP 800-53 framework. Covers baseline selection by impact level, overlay application, and tailoring documentation. Does not cover control implementation (SP 800-53 governs control descriptions) or assessment procedures (SP 800-53A).

## Workflow

1. Categorize the system per FIPS 199: confidentiality, integrity, and availability impact levels for the information types processed; the highest watermark sets the baseline candidate.
2. Select the corresponding SP 800-53B baseline (low/moderate/high) as the starting control set; document the categorization rationale because everything downstream inherits from it.
3. Apply mandated tailoring per 800-53B: assign control values, remove inappropriate controls with rationale, and apply low-impact modifications where authorized.
4. Apply overlays as conditions require: 800-53B defines overlays as fully specified control sets supplementing or modifying a baseline (privacy overlay, controlled unclassified information, and sector overlays); each applied overlay is recorded with its source.
5. Document the tailoring decision record: every addition, deletion, and parameter change with rationale and approver — the record is the system's baseline definition and survives staff changes.
6. Re-baseline on recategorization: when the system's information types or environment change materially, categorization is revisited and the baseline adjusted through the same tailoring process.
7. Feed the tailored baseline to assessment: SP 800-53A assessment objectives for the tailored control set define what evidence the system must produce.

## Controls and evidence

- FIPS 199 categorization record with impact levels per information type.
- Baseline selection record tied to categorization.
- Tailoring decision record with per-control rationale and approvals.
- Overlay application records with sources.
- Re-baselining triggers and events.

## Validation

- Confirm the current baseline matches the current categorization (no drift after system changes).
- Sample five tailoring decisions and confirm each has recorded rationale and approver.
- Confirm every applied overlay has a citable source and version.

## Failure correction

- **Baseline-categorization mismatch** → recategorize and re-baseline; the mismatch itself indicates the change-management gap that missed the recategorization.
- **Tailoring without rationale** → reconstruct rationale with decision participants or revert to baseline defaults.
- **Overlay applied informally** → formalize through the tailoring record or remove; informal overlay content drifts from its source.

## Limitations

- 800-53B defines baselines and overlays for systems under the SP 800-53 framework; other regimes map differently.
- Tailoring freedom creates responsibility: a control removed stays removed in assessments, and removing controls to reduce audit surface is visible to assessors.
- The privacy overlay interlocks with privacy program documentation; applying it pulls in privacy management obligations beyond security controls.

## Scope note

This article is part of the security leaf. Cross-reference: `NIST_SP_800_171_R3_CUI_PROTECTION_GOVERNANCE.md`, `NIST_SP_800_53A_REV5_ASSESSMENT_PROCEDURE_TEMPLATE_GOVERNANCE.md` (templates leaf), and `NIST_SP_800_37_RISK_MANAGEMENT_FRAMEWORK_TEMPLATE_GOVERNANCE.md` (templates leaf).

## Canonical sources

- NIST SP 800-53B — Control Baselines for Information Systems and Organizations (September 2020): https://csrc.nist.gov/publications/detail/sp/800-53b/final
- FIPS 199 — Standards for Security Categorization of Federal Information and Information Systems: https://csrc.nist.gov/publications/detail/fips/199/final
- NIST SP 800-53 Rev 5 — Security and Privacy Controls: https://csrc.nist.gov/pubs/sp/800/53/rev-5/final
- NIST SP 800-60 — Guide for Mapping Types of Information and Information Systems to Security Categories: https://csrc.nist.gov/publications/detail/sp/800-60/rev-1/final
- NIST SP 800-37 Rev 2 — Risk Management Framework: https://csrc.nist.gov/pubs/sp/800-37/rev-2/final
