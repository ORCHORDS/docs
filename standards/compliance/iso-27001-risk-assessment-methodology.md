# iso-27001-risk-assessment-methodology

**Issue:** Conducting ISO 27001 Clause 6.1.2 information security risk assessments
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
ISO 27001 requires a documented risk assessment process that produces consistent, comparable results. The standard is methodology-agnostic but prescribes required outputs.

## Pattern / Solution
Risk assessment framework (ISO 27005-aligned):

1. Establish context:
   - Define risk criteria: likelihood scale (1-5), impact scale (1-5), risk appetite threshold
   - Define asset scope (from ISMS scope)

2. Risk identification:
   - Identify assets (information, software, hardware, services, people)
   - Identify threats per asset (CIA triad: confidentiality, integrity, availability)
   - Identify vulnerabilities that threats could exploit

3. Risk analysis (qualitative matrix):
   - Likelihood x Impact = Risk Score (1-25)
   - Risk register format: Asset | Threat | Vulnerability | Likelihood | Impact | Risk Score | Control | Residual Risk

4. Risk evaluation:
   - Compare against risk appetite (e.g., accept <5, treat 5-14, escalate >15)
   - Risk owner assigned for each risk above appetite

5. Risk treatment (Annex A options):
   - Modify (implement controls from Annex A / ISO 27002)
   - Retain (accept with documented rationale)
   - Avoid (cease activity)
   - Share (transfer via insurance or contract)

6. Statement of Applicability (SoA):
   - All Annex A controls listed
   - For each: applicable (yes/no), implemented (yes/no/partial), justification
   - Mandatory output for certification

Review risk assessment at planned intervals (at least annually) and after significant changes.

## Gotchas
- Risk register must be living document — single point-in-time assessment fails recertification
- SoA must reference risk treatment decisions — cannot exclude controls without documented rationale
- Certification auditors trace from risk to control to SoA — gaps in the chain are major nonconformities
- Asset inventory must match ISMS scope — shadow IT is a common finding

## Related
- `iso-27001-compliance.md`
- `iso-27001-isms-scope-definition.md`
