# oauth-pushed-authorization-request-integrity

**Issue:** Sensitive OAuth authorization parameters are exposed or altered through front-channel authorization requests.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

Pushed Authorization Requests (PAR) move authorization parameters to an authenticated back-channel and return a short-lived request URI. Security depends on binding the request to the client, enforcing expiry and single-use behavior, and rejecting altered front-channel parameters.

**Source:** [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://datatracker.ietf.org/doc/rfc9126/).

## Fix

- authenticate the client at the PAR endpoint;
- validate redirect URI, scope, PKCE, and request parameters before issuing the request URI;
- enforce short expiry and single-use semantics;
- accept only the request URI in the subsequent authorization request;
- log non-sensitive correlation data and reject mismatched client or expired request URI;
- test cancellation and retry behavior without leaking authorization data.

## Verification

- Altered front-channel parameters cannot override the pushed request.
- An expired or reused request URI is rejected.
- A request URI cannot be used by another client.
- PKCE and redirect URI validation are preserved end to end.

## Related

- `security/oauth-21-2026.md`
- `security/oauth-dpop-sender-constrained-token-validation.md`
