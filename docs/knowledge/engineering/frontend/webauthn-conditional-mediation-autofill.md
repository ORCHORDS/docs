# WebAuthn conditional mediation and passkey autofill

**Issue:** A passkey-enabled login triggers a modal ceremony on page load or mistakes conditional mediation availability for authentication success.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

Conditional mediation lets a WebAuthn credential request participate in browser autofill while the user interacts with a sign-in field. It remains a complete WebAuthn assertion ceremony: the server must issue a challenge and verify the returned assertion.

**Sources:** [WebAuthn Level 3](https://www.w3.org/TR/webauthn-3/) · [Credential Management Level 1](https://www.w3.org/TR/credential-management-1/)

## Controls

- feature-detect conditional mediation and preserve a normal sign-in/passkey button fallback;
- mark the intended identifier field with the platform-supported WebAuthn autocomplete token;
- obtain a short-lived, session-bound server challenge before calling `navigator.credentials.get`;
- cancel stale requests during navigation or account-mode changes;
- verify origin, RP ID, challenge, signature, flags, and credential/account binding server-side.

## Verification

- no credential, cancellation, password selection, passkey selection, and unsupported-browser paths are usable;
- duplicate page initialization does not create competing ceremonies;
- cross-origin iframe and RP-ID boundary tests fail closed;
- autofill UI never reveals whether an arbitrary account exists.

## Gotchas

- availability checks are hints and can change with browser/provider state.
- local user verification is not backend authorization.
- do not log assertion objects or credential identifiers in client analytics.
