# magic-link-email

**Issue:** Implementing passwordless authentication via email magic links
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Magic links provide passwordless authentication by sending a one-time login link to the user's email.

## Pattern / Solution
1. User enters email; generate OTP token (CSPRNG, 32+ bytes).
2. Store hashed token with expiry (15 minutes) and user ID.
3. Send magic link email immediately.
4. On link click: verify token, create session, invalidate token, redirect.

```js
const token = crypto.randomBytes(32).toString('hex');
await db.insert('magic_links', {
  userId,
  tokenHash: sha256(token),
  expiresAt: addMinutes(new Date(), 15)
});
const link = `https://app.example.com/auth/magic?token=${token}`;
await sendEmail({ to: user.email, template: 'magic-link', data: { link } });
```

Email content: "Click to sign in — link valid for 15 minutes. Do not share this link."

## Gotchas
- Link must work on a different device/browser than where it was requested.
- Do not put the session token in the URL; use a short-lived exchange token.
- Security scanners may follow magic links; check for bot user agent or use POST-redirect pattern.
- Link expiry of 15 minutes is a good balance; shorter frustrates users, longer increases risk.

## Related
- password-reset-email, email-verification-flow, security-alert-email
