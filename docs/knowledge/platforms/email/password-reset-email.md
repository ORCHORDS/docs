# password-reset-email

**Issue:** Implementing secure, deliverable password reset emails
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Password reset emails must arrive quickly, use secure tokens, and be resistant to enumeration and phishing.

## Pattern / Solution
1. Generate cryptographic token: `crypto.randomBytes(32).toString('hex')`.
2. Store hashed token with expiry: `SHA-256(token)`, expires in 1 hour.
3. Send email immediately; queue with high priority.
4. Reset link: `https://app.yourdomain.com/auth/reset?token={{token}}`.
5. On token use: invalidate immediately (single-use).

Email content:
- Subject: "Reset your password" (direct, no ambiguity).
- Expiry time prominently displayed: "This link expires in 1 hour."
- Security notice: "If you didn't request this, you can ignore this email."
- No password in email body.

## Gotchas
- Do not confirm or deny whether an email exists in the reset flow (prevents enumeration).
- Invalidate all active reset tokens when password is successfully changed.
- Send from a trusted domain with good reputation; password resets going to spam is a critical UX failure.
- Link must work when forwarded; tokens should not be IP-bound.

## Related
- security-alert-email, email-verification-flow, magic-link-email, transactional-vs-marketing-email
