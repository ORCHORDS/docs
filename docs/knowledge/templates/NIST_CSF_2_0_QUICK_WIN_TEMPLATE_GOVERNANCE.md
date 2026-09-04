# NIST CSF 2.0 Quick-Win Template

## Purpose

Establish governance on a template artifact used to drive and record short-cycle (under 90 day) cybersecurity improvements against the NIST Cybersecurity Framework 2.0. The template is suitable for documenting and tracking "quick wins" — improvements that depend on existing capabilities, minimize new technology investment, and produce a measurable security outcome on a known schedule.

## Current status

- NIST CSF 2.0 published as final in February 2024. CSF 2.0 reorganized the Functions to include a new "Govern" function alongside the established Identify, Protect, Detect, Respond, and Recover functions.
- The CSF 2.0 reference tool provides Quick-Start Guides (QSGs) and Profiles as adoption aids; a Quick-Win worksheet is a community-standard adoption artifact rather than a NIST-blessed template with one fixed name. This template provides governance content for whichever local form an adopting program uses.
- Companion to NIST_CSF_2_0_ORGANIZATIONAL_PROFILE_TEMPLATE_GOVERNANCE.md (which covers the longer-cycle Profile) and the existing CSF2 incident-response integration template.
- Status as of 2026-09-04: CSF 2.0 is still the current NIST CSF version; no 2.1 release located at the time of writing.

## Sources

- Primary: NIST Cybersecurity Framework 2.0, https://www.nist.gov/cyberframework and https://doi.org/10.6028/NIST.CSWP.29 .
- Companion: NIST CSF 2.0 Reference Tool "Quick-Start Guide" entry points, https://csrc.nist.gov/projects/cybersecurity-framework .
- Cross-reference: NIST SP 800-53 Rev. 5 control catalogue (for subcategory-to-control mapping), NIST SP 800-66 Rev. 2 (HIPAA Security Rule mapping), NIST SP 800-171 Rev. 3 (CUI protection mapping).

## Scope note

This template governance applies to "Quick Win" Worksheet artifacts that a security program uses to plan a discrete, observable improvement mapped to the CSF 2.0 Functions / Categories / Subcategories structure. Each Quick Win row should contain these governed fields:

1. Identifier and version. A worksheet identifier (e.g., `QW-2026-Q3-014`) plus the worksheet version; each row carries the parent worksheet identifier for traceability.
2. Title and target outcome. A short human title and a one-sentence outcome: what security posture will demonstrably change at the end of the cycle.
3. CSF 2.0 subcategory mapping. Each Quick Win must be tagged with the GOVER row (if applicable) plus exactly one or more of Identify / Protect / Detect / Respond / Recover. Note that the Govern function is new in CSF 2.0; any pre-2024 worksheet using only the original five functions must be re-mapped before use.
4. Owner and approver. A single accountable owner plus a single approver who verifies the outcome. Owner and approver must not be the same individual.
5. Cycle, due date, and exit criterion. A target cycle expressed in days (recommended: 30, 60, 90) with a binary, measurable exit criterion (e.g., "MFA enforced for 100% of privileged accounts in production identity provider"). The exit criterion should be checkable from a single source of truth.
6. Evidence record. A reference to the artifact that will be produced as evidence (configuration snapshot, signed report, log extract, screenshot of dashboard state), plus retention period.
7. Dependency and risk note. Any prerequisite or known residual risk the team explicitly accepts if the Quick Win is not extended into a larger initiative.

Adoption governance for this template requires that Quick Wins roll up into a Program-Level tracker. A Quick Win that cannot be expressed within a 90-day cycle or that requires architectural change should be reclassified as a Program initiative and tracked separately. Quick Wins should not be used as a substitute for a Current Profile → Target Profile gap analysis; the Quick-Win worksheet complements, not replaces, the profile workflow covered in `NIST_CSF_2_0_ORGANIZATIONAL_PROFILE_TEMPLATE_GOVERNANCE.md`.

This template does not supersede the CSF 2.0 Reference Tool or any sector-specific overlay (e.g., NIST SP 800-66 Rev. 2 for HIPAA mapping); overlays are applied to the parent Profile, then broken into worksheets at the Quick Win level.
