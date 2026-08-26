# OAuth RFC 9470 step-up authentication challenge

**Issue:** A sensitive action needs stronger or more recent user authentication than the access token proves, but the API returns a generic denial or trusts an old session.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

RFC 9470 lets a resource server challenge a client when the token's user-authentication event is insufficient for the requested operation. It is a transaction-policy mechanism, not a replacement for authorization.

**Source:** [RFC 9470 — OAuth 2.0 Step Up Authentication Challenge Protocol](https://www.rfc-editor.org/rfc/rfc9470.html)

## Flow

1. The resource server evaluates the operation’s policy: required authentication context and/or recency.
2. If the presented token fails, respond with `401` and `WWW-Authenticate: Bearer error="insufficient_user_authentication"`, including `acr_values` and/or `max_age` as appropriate.
3. The client requests a new authorization result using the challenge requirements.
4. The authorization server performs the necessary user interaction and returns a token carrying authentication-event information.
5. The resource server validates normal token properties plus `acr` and `auth_time` (or equivalent introspection information) before performing the action.

## Controls

- make the action-to-assurance policy explicit and owned;
- bind step-up to the exact sensitive action; never treat it as blanket authorization;
- enforce issuer, audience, expiry, scope, subject, `acr`, and `auth_time`;
- use a short, purpose-bound confirmation window for irreversible transactions;
- rate-limit and audit challenges without logging access tokens or personal authentication data.

## Verification

- an old but otherwise valid token is challenged for a high-risk action;
- a newly authenticated token meeting policy succeeds;
- a token with correct scope but inadequate assurance is rejected;
- challenge loops, stale return URLs, and cross-account resumption fail safely;
- standard low-risk requests remain usable without unnecessary prompts.

## Related

- `security/oauth-dpop-sender-constrained-token-validation.md`
- `security/passkeys-2026.md`
- `payments/strong-customer-authentication.md`
