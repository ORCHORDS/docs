# email-verification-flow

**Issue:** Implementing email address verification during signup and address changes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Unverified email addresses lead to hard bounces, bad data, and accounts that cannot receive communications.

## Pattern / Solution
1. On signup: create user with `email_verified: false`.
2. Generate verification token (same as password reset pattern), send verification email.
3. Verification link: `https://app.yourdomain.com/verify?token={{token}}`.
4. On click: mark `email_verified: true`, invalidate token.
5. Gate features on verified status; send reminders at 24h and 72h if unverified.

Resend flow: expose "Resend verification email" button; rate-limit to 1 per 5 minutes.

On email change:
- New email unverified until confirmed.
- Send verification to new address.
- Keep old email active until new one verified.
- Notify old email of the change.

## Gotchas
- Verification tokens should be single-use and expire in 24 hours.
- Do not block critical transactional emails (receipts, password reset) on verification status.
- Some signup flows verify email before allowing password set (better UX for invite flows).

## Related
- double-opt-in-flow, password-reset-email, magic-link-email, security-alert-email
