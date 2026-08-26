# gdpr-email-consent

**Issue:** Documenting and managing email consent records under GDPR
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Sending marketing email to EU/UK residents without a documented lawful basis exposes you to GDPR enforcement.

## Pattern / Solution
Lawful bases for email marketing under GDPR:
1. **Consent** (Art. 6(1)(a)) — explicit, specific, freely given, informed, and documented
2. **Legitimate interest** (Art. 6(1)(f)) — for existing customers re: similar products (soft opt-in under PECR)

Consent record schema:
```sql
CREATE TABLE consent_records (
  id             BIGSERIAL PRIMARY KEY,
  email          TEXT NOT NULL,
  consent_type   TEXT NOT NULL, -- 'marketing', 'newsletter', 'product_updates'
  lawful_basis   TEXT NOT NULL, -- 'consent', 'legitimate_interest'
  given_at       TIMESTAMPTZ NOT NULL,
  ip_address     INET,
  user_agent     TEXT,
  source         TEXT,          -- 'signup_form_v2', 'checkout_checkbox'
  form_copy      TEXT,          -- exact wording shown to user at time of consent
  withdrawn_at   TIMESTAMPTZ,
  withdrawn_via  TEXT           -- 'unsubscribe_link', 'preference_center', 'support_request'
);
```

On signup form, the consent checkbox must:
- Be unchecked by default
- Have plain-language description: "Send me product news and offers (you can opt out any time)"
- Not be bundled with terms acceptance

Right to erasure: when a user exercises the right to be forgotten, pseudonymize or delete the email while retaining the consent record (with email replaced by a hash) for legal documentation.

## Gotchas
- Pre-ticked boxes are not valid consent under GDPR
- Consent obtained before GDPR (May 2018) may not meet the standard; re-consent campaigns were commonly run in 2018
- Consent must be as easy to withdraw as to give; the withdrawal path must be documented

## Related
- `double-opt-in-flow.md`
- `can-spam-compliance.md`
- `casl-canada-compliance.md`
