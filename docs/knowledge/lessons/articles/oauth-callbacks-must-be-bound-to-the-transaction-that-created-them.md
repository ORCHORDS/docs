# OAuth Callbacks Must Be Bound to the Transaction That Created Them

**Issue:** An OAuth/OIDC client accepts a valid-looking authorization response without proving that the same browser session initiated the corresponding authorization transaction.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP ASVS 5.0.0 V10.1.2 requires values returned from the authorization server to be accepted only when they belong to a flow initiated by the same user-agent session and transaction. V10.2.1 additionally requires browser-based request-forgery protection for OAuth authorization-code clients using PKCE or validated `state` as applicable. A valid code or token is not enough if it can be attached to the wrong transaction or browser session.

## Engineering rule

- Generate transaction-binding values such as PKCE `code_verifier`, OAuth `state`, and OIDC `nonce` with sufficient unpredictability.
- Make those values specific to one authorization transaction and bind them to the client and originating user-agent session.
- Reject callbacks with missing, wrong, stale, replayed, or cross-transaction binding values.
- For authorization-code flows, implement CSRF protection through PKCE or validated `state` according to the client design.
- Do not continue to token exchange or authenticated application state after binding validation fails.

## Verification

- Start two authorization attempts in parallel and attempt to swap callback values between them.
- Replay a previously accepted callback/binding value and confirm rejection.
- Supply an incorrect PKCE verifier, `state`, or OIDC `nonce` as applicable and confirm the flow stops before authentication completes.

## Official source

- OWASP ASVS 5.0.0 requirements V10.1.2 and V10.2.1: https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.csv
