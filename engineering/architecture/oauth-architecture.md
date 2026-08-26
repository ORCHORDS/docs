# oauth-architecture

**Issue:** Applications store user credentials directly instead of delegating authentication
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An integration requires a user to provide their password to a third-party app, which stores it in plaintext to call the primary API.

## Pattern / Solution
Use OAuth 2.0 authorization code flow with PKCE for user-facing applications. Issue short-lived access tokens and longer-lived refresh tokens. Scope tokens to the minimum required permissions. Use OIDC for identity assertions.

## Gotchas
Implicit flow is deprecated and insecure. Token storage in localStorage is vulnerable to XSS. Validate the state parameter to prevent CSRF. Rotate refresh tokens on use.

## Related
api-security-architecture, zero-trust-architecture, api-gateway-pattern
