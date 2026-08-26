# pipeda-canada-compliance

**Issue:** Canada PIPEDA and Quebec Law 25 (Bill 64) privacy compliance requirements
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
PIPEDA governs private-sector personal information in the course of commercial activity. Quebec Law 25 (Bill 64) adds GDPR-like requirements including PIAs, breach reporting, and data portability. Bill C-27 (CPPA) may replace PIPEDA — monitor for enactment.

## Pattern / Solution
PIPEDA 10 Fair Information Principles:
1. Accountability — designate a privacy officer; publish name/contact
2. Identifying purposes — state purpose before or at collection
3. Consent — obtain meaningful, informed consent (express for sensitive data)
4. Limiting collection — collect only what is necessary
5. Limiting use, disclosure, and retention — do not repurpose without consent
6. Accuracy — keep data accurate, complete, up to date
7. Safeguards — technical, physical, and administrative security
8. Openness — publish accessible privacy policy
9. Individual access — respond within 30 days; fee cannot exceed minimal cost
10. Challenging compliance — maintain complaints process; investigate and address

Quebec Law 25 additions (all in force Sept 2023):
- Privacy Impact Assessment (PIA) required for new tech systems and cross-border transfers
- Breach notification to Commission d'acces a l'information (CAI) within reasonable time (target 72h) and to individuals when risk of serious injury
- Data portability: provide computerized personal information in structured format on request
- Automated decision-making: inform individuals; provide explanation and right to resubmission on request
- Privacy Officer: publicly identified by name

## Gotchas
- PIPEDA may not apply for intra-provincial activities in Alberta, BC, and Quebec (substantially similar provincial laws)
- Meaningful consent is contextual: obvious purposes need less formality; sensitive data needs express consent
- Bill C-27 could significantly change the landscape — track Parliament progress
- OPC (federal) and provincial commissioners have concurrent jurisdiction in some cases

## Related
- `gdpr-privacy-notice-template.md`
- `lgpd-brazil-compliance.md`
