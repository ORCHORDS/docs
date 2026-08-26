# security-alert-email

**Issue:** Sending security notification emails for suspicious or significant account events
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Users must be notified of security events (new login, password change, email change) to detect unauthorized access.

## Pattern / Solution
Events requiring security emails:
- New device/location login (if anomalous).
- Password changed.
- Email address changed.
- MFA enabled/disabled.
- API key created.
- Account deletion initiated.

Template pattern:
- Subject: "Security alert: [action] on your account" — clear, not alarming.
- Body: What happened, when, where (IP, device, location if available).
- Action: If this was you, no action needed. If not, link to secure account.
- Timing: Send immediately; do not queue behind marketing delays.

## Gotchas
- Security emails must bypass marketing suppression lists; they are transactional.
- Do not include the new password, API key, or sensitive data in the email body.
- Send to both old and new address when email is changed.
- Rate-limit security emails per user to prevent alert fatigue from credential stuffing attacks.

## Related
- password-reset-email, email-verification-flow, transactional-vs-marketing-email
