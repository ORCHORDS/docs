# Gmail email action markup registration and safety

**Issue:** Structured email actions can place a button near a message, but an unsafe or stale action URL can bypass context, expose identifiers, or perform a state change without adequate confirmation.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented — Gmail-specific and subject to sender registration/eligibility

## Decision

Use Gmail action markup only as a convenience entry point into the same authenticated, authorized, idempotent server workflow used by the website. The ordinary email body and link remain the portable baseline.

## Controls

- Complete Google’s sender registration and meet its quality/authentication requirements before production.
- Generate markup from a typed schema and validate it before send.
- Use HTTPS URLs on controlled domains and short-lived opaque references rather than raw personal data.
- Require authentication and current authorization for sensitive actions.
- Use confirmation for destructive or financial state changes.
- Make idempotency explicit when an action can be retried.
- Bind the action to the intended resource, tenant, and permitted transition.
- Expire links and return a safe explanatory page after completion or expiry.
- Never treat markup rendering as proof of message delivery or identity.

## Verification

Validate schema syntax, registration status, SPF/DKIM/DMARC alignment, expired and replayed tokens, wrong-account access, duplicate invocation, and unsupported clients. Confirm that previewing or link scanning cannot complete the business action. Exercise revocation after account or resource state changes.

## Gotchas

Mailbox providers may suppress markup even when valid. Automated scanners can fetch URLs before a person clicks. GET requests must not perform unsafe changes. Provider registration and supported action types can change; recheck current documentation before launch.

## Sources

- [Google Gmail Email Markup](https://developers.google.com/gmail/markup)
- [Google: Register with Gmail for email markup](https://developers.google.com/gmail/markup/registering-with-google)
- [Google: Email actions](https://developers.google.com/gmail/markup/actions/actions-overview)
