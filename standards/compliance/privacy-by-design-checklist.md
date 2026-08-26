# privacy-by-design-checklist

**Issue:** Embedding privacy controls at design time (GDPR Art. 25 — Data Protection by Design and by Default)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Art. 25 requires controllers to implement data protection by design (DPbD) and by default. "By default" means only the minimum personal data necessary for each specific purpose is processed without user action. Regulators increasingly request evidence of DPbD in audit inquiries and DPIA reviews. This checklist is intended for use during product design reviews and sprint planning.

## Pattern / Solution
**Privacy by design review — gate before feature launch:**

**1. Data minimisation**
- [ ] Can the feature achieve its purpose with less data or with pseudonymous identifiers?
- [ ] Are all collected fields actually read by the application?
- [ ] Is collection optional where the feature works without it?

**2. Purpose limitation**
- [ ] Is each data field linked to exactly one stated processing purpose?
- [ ] Will data collected for this feature be shared with other features or teams? If yes, document the additional purpose and legal basis.

**3. Storage limitation**
- [ ] Is a retention period defined and enforced for every new data type?
- [ ] Will automated deletion be triggered, or does it require manual action?

**4. Access control defaults**
- [ ] Is data private by default? (User must opt in to sharing, not opt out.)
- [ ] Are new API endpoints private unless explicitly opened?
- [ ] Does the feature expose data in URLs, logs, or error messages?

**5. Encryption and security**
- [ ] Is new data encrypted at rest (AES-256 or equivalent)?
- [ ] Is all transmission over TLS 1.2+?
- [ ] Is PII excluded from logging and analytics pipelines?

**6. Third-party data sharing**
- [ ] Does the feature require sharing data with a new sub-processor?
- [ ] Is a DPA/BAA in place before data is shared?

**7. User transparency**
- [ ] Is the new data collection disclosed in the privacy notice?
- [ ] Is the legal basis documented in the ROPA (Record of Processing Activities)?

**8. DPIA trigger assessment**
- [ ] Does the feature involve: (a) large-scale processing of sensitive data, (b) systematic monitoring of publicly accessible areas, or (c) automated decision-making with legal effects?
  - If yes → conduct a Data Protection Impact Assessment before deployment.

**Default settings checklist:**
```
Analytics: OFF by default (opt-in)
Marketing emails: OFF by default (opt-in)
Profile visibility: PRIVATE by default
Data export sharing: DISABLED by default
Diagnostic telemetry: Anonymised by default, or OFF
```

## Gotchas
- "By default" is stricter than "by design" — it means the most privacy-protective option must be the one active without any user action.
- DPIA is not optional for high-risk processing; regulators have issued fines specifically for missing DPIAs.
- Privacy notices must be updated before — not after — a new data processing activity begins.
- Retrospective privacy reviews ("we'll add privacy later") are explicitly against Art. 25 intent and are cited as aggravating factors in enforcement decisions.

## Related
- `gdpr-data-retention-policy.md`
- `gdpr-consent-management.md`
- `data-classification-policy.md`
- `gdpr-dpa-standard-contractual-clauses.md`
