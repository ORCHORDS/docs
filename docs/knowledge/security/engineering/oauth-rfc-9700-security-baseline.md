# OAuth RFC 9700 security baseline

**Issue:** OAuth deployments retain legacy flows and loose redirect handling even though current IETF guidance deprecates or constrains them.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Adopt RFC 9700 / BCP 240 as the current security baseline. Use authorization code flow with transaction-bound PKCE, exact redirect URI matching, no open redirectors, and authorization-server metadata. Do not pass access tokens in query parameters. Avoid implicit grant unless exceptional mitigations satisfy the BCP. Prefer asymmetric client authentication and sender-constrained tokens for high-value APIs. Rotate or bind refresh tokens and expire inactive grants.

## Verification

Test redirect variants, mix-up, code injection, PKCE downgrade, token replay, open redirect, refresh replay, and logout/password-change revocation. Confirm authorization endpoints do not use HTTP 307 when credentials could be reposted.

## Gotchas

PKCE must be transaction-specific. TLS alone does not stop leaked bearer-token replay. OAuth authorization and OpenID Connect authentication are related but distinct.

## Sources

- [RFC 9700 / BCP 240](https://www.rfc-editor.org/info/rfc9700/)
