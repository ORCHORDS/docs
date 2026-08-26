# iso-27002-2022-new-controls

**Issue:** Implementing the 11 new controls introduced in ISO 27002:2022
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
ISO 27002:2022 restructured from 114 controls in 14 domains to 93 controls in 4 themes. It added 11 new controls that must be addressed in the Statement of Applicability (SoA) for ISO 27001 certifications or renewals.

## Pattern / Solution
The 11 new controls:
1. 5.7 Threat intelligence — collect and analyze threat intel; subscribe to ISAC feeds; act on relevant threats
2. 5.23 Information security for cloud services — cloud-specific controls in vendor agreements; shared responsibility model documented
3. 5.30 ICT readiness for business continuity — IT recovery integrated with BCP; RTO/RPO per system
4. 7.4 Physical security monitoring — CCTV, access logs for server rooms; visitor logs
5. 8.9 Configuration management — baseline configs documented; drift detection; IaC enforced
6. 8.10 Information deletion — secure deletion procedures; certificate of destruction for hardware
7. 8.11 Data masking — production data not used in non-production without masking/anonymization
8. 8.12 Data leakage prevention — DLP tools on email and endpoints; classification-enforced controls
9. 8.16 Monitoring activities — security monitoring for all in-scope systems; log review cadence
10. 8.23 Web filtering — block known-malicious domains; content filtering on corporate network
11. 8.28 Secure coding — OWASP guidelines; security code review; SAST/DAST in CI/CD pipeline

Transition deadline: Organizations certified to ISO 27001:2013 had until October 2025 to transition to 27001:2022 (which references 27002:2022). All new certifications use 2022 standard.

## Gotchas
- Old Annex A numbering no longer valid — SoA must use 2022 control numbers
- "Not applicable" for any new control requires written justification in SoA
- Control 8.11 (data masking) catches many orgs using prod data in dev/staging
- Control 5.7 (threat intelligence) requires active subscription and response evidence, not just signing up

## Related
- `iso-27001-risk-assessment-methodology.md`
- `iso-27017-cloud-security.md`
