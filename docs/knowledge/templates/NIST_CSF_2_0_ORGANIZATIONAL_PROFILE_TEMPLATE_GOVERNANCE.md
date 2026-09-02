# NIST CSF 2.0 Organizational Profile Template Governance

## Purpose

NIST Cybersecurity Framework (CSF) 2.0 (NIST, February 2024) provides a common language for organizing cybersecurity risk into six Functions: Govern, Identify, Protect, Detect, Respond, Recover. A reusable CSF 2.0 organizational profile template records, for each Function and Category, the organization's current tier (Tier 1: Partial, Tier 2: Risk Informed, Tier 3: Repeatable, Tier 4: Adaptive) and the target tier, the current implementation status for representative Subcategories, the gap description, and the roadmap to reach the target tier. The profile converts the CSF from a reference framework into an auditable, comparable artifact suitable for board-level cybersecurity reporting and regulatory mapping.

The template must remain generic: it MUST NOT embed real organization identifiers, current tier ratings that identify a specific entity, or gap descriptions that disclose internal posture.

## Scope

This template applies to NIST CSF 2.0 organizational profiles (sometimes called "Current" and "Target" profiles). It does not address CSF 1.1 profiles (which lack the Govern Function); a separate template is required for legacy evaluations. The template does not address Community Profiles (which are sector-specific baseline profiles authored by industry working groups); those profiles are referenced as inputs but the organization-specific profile is captured here.

## Workflow

1. Open the template and complete the header with the profile identifier, the CSF version (2.0), the assessment date, the assessor, the scope (business units, geographies, systems), and the target tier.
2. For each Function (Govern, Identify, Protect, Detect, Respond, Recover), record the Function-level current tier and target tier.
3. For each Category within a Function (for example GV.OC Organizational Context, ID.AM Asset Management, PR.AA Identity and Authentication), record:
   - Category identifier and title.
   - Current tier and target tier at the Category level.
   - Representative Subcategories with implementation status: implemented, partially implemented, not implemented, not applicable.
   - Evidence references for implemented Subcategories.
   - Gap descriptions and remediation owners for non-implemented Subcategories.
4. Identify priority gaps and align them with the cybersecurity roadmap.
5. Record the priority Subcategories for board-level reporting (typically the highest-residual-risk ones).
6. Save the completed template alongside the cybersecurity strategy and risk register, with access restricted to the security steering committee and the board's audit committee.

## Controls and evidence

- Header records profile identifier, version, target tier, scope, date, and assessor.
- Function-level tier ratings recorded for both current and target.
- Category-level tier ratings recorded.
- Subcategory rows record status, evidence, and gap remediation owner.
- Cybersecurity roadmap records priority gaps with target dates.

## Validation

- Every Function and Category is addressed; no element is left blank without a documented justification.
- Tier ratings at the Category level are consistent with the Function-level ratings.
- Subcategory evidence references are precise (policy identifier, configuration baseline, log source).
- Priority Subcategories are mapped to the cybersecurity roadmap.
- The profile is reviewed annually or after a significant change in scope.

## Failure correction

Common defects include selecting Tier 3 ratings without Subcategory-level evidence, leaving Categories at Tier 1 without a remediation plan, and using the CSF as a compliance checklist rather than a risk-management framewor. Corrective actions include requiring Subcategory-level evidence for any Tier 3 or Tier 4 rating, linking Tier 1 categories to the roadmap, and framing the profile as a risk-management conversation rather than a compliance audit.

## Limitations

- The template does not substitute for a CSF Implementation Tier assessment, which uses the Govern Function characteristics (GV.OC, GV.RM, GV.RR, GV.SC, GV.PO, GV.OV, GV.MT).
- It does not address the Quick-Start Guide for CSF 2.0; a separate template is required for small-business adoption.
- It does not address the Informative References mapping (CSF Subcategories to NIST SP 800-53, ISO/IEC 27002, etc.); mapping tables are governed by a separate template.
- It does not cover the CSF 2.0 Reference Tool export format.

## Scope note

This template is part of the **templates** leaf. Sibling leaves cover: **security** (control selection and tier assessment), **standards** (CSF 2.0 relationships to NIST SP 800-53 and ISO/IEC 27001), **business** (board-level cybersecurity reporting), and **operations** (cybersecurity roadmap tracking). The template should be used together with those sibling-leaf articles.

## Canonical sources

- NIST Cybersecurity Framework 2.0 (NIST, February 2024): https://www.nist.gov/cyberframework
- NIST CSF 2.0 Reference Tool (NIST): https://csrc.nist.gov/Projects/Cybersecurity-Framework/Filters
- NIST SP 800-53 Control Mappings (NIST): https://csrc.nist.gov/Projects/Cybersecurity-Framework/Filters

Sources were verified on September 1, 2026.