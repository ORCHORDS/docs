# gdpr-privacy-notice-template

**Issue:** Structuring GDPR-compliant privacy notices under Articles 13 and 14
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
GDPR Articles 13 (data collected directly) and 14 (data from third parties) require specific disclosures at the point of collection. Many organizations produce walls of legal text that fail the transparency requirement.

## Pattern / Solution
Use a layered notice approach:

Layer 1 — Short notice (shown at collection point):
```
We collect your email to send order confirmations and service updates.
Legal basis: contract. Retention: 3 years post-last-purchase.
Full privacy policy: [link]
```

Layer 2 — Full privacy policy must include:
- Controller identity and contact (+ DPO contact if applicable)
- Purposes and legal bases for each processing activity
- Recipients / categories of recipients (including processors and third countries)
- Retention periods per category
- Data subject rights: access, rectification, erasure, restriction, portability, objection, withdraw consent
- Right to lodge complaint with supervisory authority
- Whether provision is statutory/contractual and consequences of not providing
- Existence of automated decision-making and meaningful information about logic

Article 14 additional disclosures (third-party sourced data):
- Categories of personal data
- Source (specific or category of source)
- Must deliver within 1 month of obtaining, or at first communication

## Gotchas
- Vague language like "improve our services" is not a valid purpose — be specific
- Each language/market variant must be reviewed for local law additions
- Updating the notice does not automatically satisfy a new lawful basis requirement — reconsent may be needed
- Cookie notices are separate from the privacy policy but must link to it

## Related
- `gdpr-consent-management.md`
- `gdpr-dpo-role-requirements.md`
- `gdpr-cookie-consent-implementation.md`
