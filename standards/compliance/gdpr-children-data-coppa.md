# gdpr-children-data-coppa

**Issue:** Overlapping obligations for children data under GDPR Article 8 and US COPPA
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Global products must comply with GDPR (consent age 13-16 depending on member state) and COPPA (under 13 in US) simultaneously. Conflicts arise in age thresholds and verification mechanisms.

## Pattern / Solution
Age threshold matrix:
- Under 13: parental consent required in all jurisdictions (COPPA + GDPR all member states)
- 13-15: parental consent required in most EU member states (DE, FR, NL, BE, AT = 16; DK, SE, FI = 13)
- 16+: self-consent in all EU jurisdictions

Safe global default: treat under-16 as requiring parental consent.

Implementation:
- Date-of-birth input on registration (not a checkbox stating age)
- If underage detected: suspend account, trigger parental consent flow
- Parental consent methods (COPPA-compliant): signed form, credit card verification, video call, government ID scan
- Do not install tracking cookies or behavioral advertising for known child users
- No public display of child personal information

Data minimization for children:
- Collect only data necessary for the service
- No persistent identifiers for advertising purposes
- No sharing with ad networks

## Gotchas
- COPPA applies to sites directed at children OR with actual knowledge of child users — mixed-audience sites must take extra care
- Age screens (checkboxes) do not satisfy COPPA without reasonable verification
- GDPR national age of consent varies — check each member state individually
- FTC COPPA enforcement is active; fines in millions for violations

## Related
- `coppa-compliance.md`
- `age-gating.md`
