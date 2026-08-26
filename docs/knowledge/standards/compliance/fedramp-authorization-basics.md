# fedramp-authorization-basics

**Issue:** Understanding FedRAMP authorization types, levels, and the authorization process
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cloud Service Providers (CSPs) selling to US federal agencies must achieve FedRAMP authorization. The process is lengthy and expensive; understanding the path before starting saves significant time.

## Pattern / Solution
Authorization paths:
1. Agency Authorization (most common): One federal agency sponsors and authorizes; ATO (Authority to Operate) issued by that agency; reused by other agencies
2. Joint Authorization Board (JAB): Three agencies (DoD, DHS, GSA) jointly review; P-ATO (Provisional ATO) issued; higher credibility but longer process (12-18 months)
3. FedRAMP Ready: Readiness Assessment Report (RAR) reviewed by FedRAMP PMO; listed in marketplace as Ready but not yet authorized

Impact levels:
- Low: non-sensitive public data (FIPS 199 Low)
- Moderate: most federal systems (FIPS 199 Moderate) — 325+ controls from NIST 800-53
- High: law enforcement, emergency services (FIPS 199 High) — 420+ controls

Authorization process steps:
1. Readiness Assessment (optional but recommended): third-party assessment of basic capabilities
2. Pre-authorization: partner with a sponsoring agency or JAB; select accredited 3PAO (Third-Party Assessment Organization)
3. Full Security Assessment: 3PAO conducts testing; produces Security Assessment Report (SAR)
4. Authorization: AO reviews Package (SSP + SAR + POA&M); issues ATO
5. Continuous monitoring: monthly and annual reporting; ongoing 3PAO assessments

Key documents: System Security Plan (SSP), Security Assessment Plan (SAP), SAR, Plan of Action and Milestones (POA&M).

## Gotchas
- 3PAO must be FedRAMP-accredited — verify at marketplace.fedramp.gov
- SSP alone is often 300+ pages — start documentation 6 months before assessment
- Penetration testing must use FedRAMP-specific rules of engagement
- Authorization does not auto-renew — ConMon (continuous monitoring) is ongoing

## Related
- `fedramp-compliance.md`
- `nist-800-53-control-families.md`
