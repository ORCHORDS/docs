---
title: "Token Storage Best Practices Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF OAuth WG guidance (RFC 8252, draft-ietf-oauth-browser-based-apps, draft-ietf-oauth-v2-1); OWASP Cheat Sheets"
---

# Token Storage Best Practices Reference Card

## Scope

Reference card for token storage best practices for OAuth 2.0/2.1 access tokens, refresh tokens, and ID Tokens. The guidance differs by client type: native applications should use the platform secure storage (Keychain on iOS, Keystore on Android), single-page applications should keep tokens in memory and rely on the backend for refresh, and server-side applications should encrypt tokens at rest with envelope encryption and avoid putting tokens in URLs, logs, or error messages. Profiles that govern token handling should cite this card and bind to OAuth 2.1, OpenID Connect Core 1.0, FAPI 2.0, and RFC 9700.

## Identifier table

| Field | Value |
| --- | --- |
| Primary documents | RFC 8252, draft-ietf-oauth-v2-1, OWASP Authentication Cheat Sheet, OWASP JWT Cheat Sheet |
| Status | Guidance maintained by IETF OAuth WG and OWASP |
| Companion artifacts | OAuth 2.1, OpenID Connect Core 1.0, FAPI 2.0, RFC 9700 |
| Source URL | https://datatracker.ietf.org/doc/draft-ietf-oauth-browser-based-apps/ |

## Plan

1. Reference this card whenever a profile governs token storage in any client type.
2. For native applications, use the platform secure storage (Keychain on iOS with `kSecAttrAccessibleWhenUnlockedThisDeviceOnly`, Keystore on Android with `setUserAuthenticationRequired`).
3. For single-page applications (SPAs), keep tokens in memory; do not persist tokens in `localStorage`, `sessionStorage`, or cookies without explicit security attributes.
4. For SPAs, use the backend-for-frontend (BFF) pattern with HTTP-only, Secure, SameSite=Strict session cookies.
5. For server-side applications, encrypt tokens at rest with envelope encryption (KMS-managed data keys).
6. Never put tokens in URLs, query strings, referrer headers, or HTML body content.
7. Never log tokens; redact tokens in error messages and audit logs.
8. Apply short access-token lifetimes with refresh-token rotation and theft detection (RFC 9700).
9. Bind to OAuth 2.1, OpenID Connect Core 1.0, FAPI 2.0, and RFC 9700.
10. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- IETF RFC 8252 (OAuth 2.0 for Browser-Based Apps) and the current OAuth 2.1 draft.
- OWASP Authentication and JWT cheat sheets.
- Client inventory with platform, storage capability, and threat model.
- Platform secure-storage API documentation (Keychain, Keystore, Windows DPAPI, TPM 2.0).
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats this card as the canonical reference for token storage across client types. Profiles that store or transmit tokens should reference this card, use platform secure storage for native clients, use the BFF pattern with HTTP-only cookies for SPAs, encrypt tokens at rest with envelope encryption for server-side applications, never log tokens, and bind to OAuth 2.1, OpenID Connect Core 1.0, FAPI 2.0, and RFC 9700.

A profile that stores tokens in browser `localStorage`, query strings, or unencrypted server-side storage is non-conformant.

## Implementation Notes

- `localStorage` and `sessionStorage` are accessible to any script running on the same origin; XSS exposes all stored tokens.
- The BFF pattern keeps tokens on the server-side and exposes only a session cookie to the SPA, which prevents XSS-based token theft.
- HTTP-only cookies are not accessible to JavaScript, mitigating XSS-based theft; `Secure` and `SameSite=Strict` attributes are required.
- Refresh-token rotation with theft detection triggers client-wide revocation when a previously rotated token is presented.
- Sender-constrained tokens (mTLS, DPoP) prevent token theft from being sufficient for misuse.
- Encryption-at-rest keys must be rotated per the key-management policy; treat token-storage key compromise as a high-severity incident.

## Companion Documents

- [IETF OAuth 2.1 Authorization Framework](IETF_OAUTH_2_1_AUTHORIZATION_FRAMEWORK.md)
- [OpenID Connect Core 1.0](OPENID_CONNECT_CORE_1_0.md)
- [FAPI 2.0 Security Profile](FAPI_2_0_SECURITY_PROFILE.md)
- [IETF RFC 9700 OAuth 2.0 Security BCP](IETF_RFC_9700_OAUTH_2_0_SECURITY_BCP.md)
- [HashiCorp Vault Rotation Best Practices](HASHICORP_VAULT_ROTATION_BEST_PRACTICES.md)
- [NIST SP 800-57 Key Management Version Governance](../reference/NIST_SP_800_57_KEY_MANAGEMENT_VERSION_GOVERNANCE.md)
- [NIST SP 800-53 Rev. 5 Access Control Family](../reference/NIST_SP_800_53_REV_5_ACCESS_CONTROL_FAMILY.md)
