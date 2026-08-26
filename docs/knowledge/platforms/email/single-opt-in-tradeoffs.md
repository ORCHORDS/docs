# single-opt-in-tradeoffs

**Issue:** Understanding when single opt-in is acceptable and what mitigations are required
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Double opt-in reduces list growth by 20–40%; product teams push for single opt-in but deliverability risk is not understood.

## Pattern / Solution
Single opt-in (SOI): add the address directly to the active list without email confirmation.

When SOI is defensible:
- Low-friction B2C product with immediate value (e.g., magic link login)
- Address was already verified as part of a purchase flow
- Transactional email only (no marketing)

When SOI adds significant risk:
- Open marketing signup forms (bots and manual abuse common)
- High-volume campaigns to cold lists
- EU/UK recipients (GDPR consent documentation is harder without a confirmation record)

Mitigations if you use SOI:
```javascript
// 1. Real-time email validation API at signup
// 2. CAPTCHA or honeypot field
// 3. Rate-limit signups per IP
// 4. Send a welcome email and monitor bounce rate immediately
// 5. Suppress anyone who hard-bounces on the welcome
app.post('/signup', rateLimiter, validateEmail, async (req, res) => {
  const { email } = req.body;
  await db.subscribers.insert({ email, status: 'active', source: 'soi' });
  await sendWelcomeEmail(email); // watch this bounce rate closely
  res.json({ ok: true });
});
```

## Gotchas
- CASL (Canada) and GDPR do not technically require double opt-in, but both require documented proof of consent; SOI makes this harder to prove
- B2B signup forms are higher risk for SOI because corporate email addresses are frequently used by colleagues to sign up others without consent

## Related
- `double-opt-in-flow.md`
- `gdpr-email-consent.md`
- `casl-canada-compliance.md`
