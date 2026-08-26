# email-list-hygiene

**Issue:** Keeping a mailing list clean to maintain deliverability and reduce costs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
List grows stale over time; sending to old addresses drives up bounce rates and dilutes engagement metrics.

## Pattern / Solution
**Validation at acquisition** — reject or flag invalid addresses on signup:
```javascript
// Simple regex (not exhaustive)
const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
// Better: use a validation API (ZeroBounce, NeverBounce, Abstract API)
const { data } = await axios.get(`https://emailvalidation.abstractapi.com/v1/?api_key=<redacted-secret>
if (data.deliverability !== 'DELIVERABLE') throw new Error('Invalid email');
```

**Periodic list cleaning** schedule:
- Monthly: remove all hard bounces (should be real-time via webhook)
- Quarterly: run full list through a validation service; remove unknowns/risky
- Every 6 months: sunset disengaged subscribers (no open/click in 180 days)

**Re-engagement before sunsetting**:
1. Send 2–3 "We miss you" emails to inactive subscribers
2. Include a prominent "Stay subscribed" CTA
3. Suppress those who do not engage

Common disposable domain list to block at signup:
- `mailinator.com`, `guerrillamail.com`, `temp-mail.org`, `throwam.com`

## Gotchas
- Bulk validation services flag role-based addresses (`info@`, `admin@`) as risky; these can be valid business contacts — review manually
- Apple Mail Privacy Protection (MPP) inflates open rates; use click-based engagement as the primary hygiene signal
- Some validation APIs have high false-positive rates on new domain extensions; cross-check multiple services

## Related
- `bounce-handling-hard-soft.md`
- `double-opt-in-flow.md`
- `email-sunset-policy.md`
