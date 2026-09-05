---
title: "IETF RFC 9700 OAuth 2.0 Security Best Current Practice Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 9700; https://www.rfc-editor.org/rfc/rfc9700.html"
---

# IETF RFC 9700 OAuth 2.0 Security Best Current Practice Reference Card

## Scope

Reference card for IETF RFC 9700, "Best Current Practice (BCP) for OAuth 2.0 Security," which updates and supersedes RFC 6819 (OAuth 2.0 Threat Model). RFC 9700 consolidates OAuth 2.0 attack-surface guidance and recommends PKCE for all clients, sender-constrained tokens, exact redirect URI matching, refresh-token rotation with theft detection, and the prohibition of the implicit and resource-owner password credentials grants for new deployments. Profiles that govern OAuth 2.0/2.1 deployments should cite RFC 9700 and bind to OAuth 2.1, OpenID Connect Core 1.0, and FAPI 2.0.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 9700, "Best Current Practice for OAuth 2.0 Security" |
| Status | Internet Best Current Practice (BCP 240) |
| Obsoletes | RFC 6819 |
| Companion artifacts | OAuth 2.1, OpenID Connect Core 1.0, FAPI 2.0, RFC 7636, RFC 8705, RFC 9449 |
| Source URL | https://www.rfc-editor.org/rfc/rfc9700.html |

## Plan

1. Reference RFC 9700 by errata whenever a profile governs an OAuth 2.0 or 2.1 deployment.
2. Mandate PKCE (RFC 7636) for every client, including confidential clients.
3. Mandate exact redirect URI match on every authorization request.
4. Prohibit the implicit grant and the resource-owner password credentials (ROPC) grant for new deployments; document exceptions with approver, scope, expiration, and compensating controls.
5. Implement refresh-token rotation with theft detection and automatic client revocation on reuse.
6. Prefer sender-constrained tokens (mTLS via RFC 8705 or DPoP via RFC 9449) for high-risk APIs.
7. Validate audience (`aud`) and issuer (`iss`) on every access token and ID Token.
8. Document scope-of-access tokens; do not issue access tokens with excessive scope.
9. Bind to OAuth 2.1 for the underlying authorization framework.
10. Bind to FAPI 2.0 when the API is regulated or financial.
11. Bind to OpenID Connect Core 1.0 when authentication is delegated.
12. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- RFC 9700 specification.
- Authorization-server policy: PKCE requirement, redirect URI matching, refresh-token rotation policy, sender-constrained token support.
- Client inventory with confidential vs public classification, scope usage, and grant types in use.
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats RFC 9700 as the canonical security reference for OAuth 2.0/2.1 deployments. Profiles that delegate authorization should cite RFC 9700 by errata, mandate PKCE for all clients, mandate exact redirect URI matching, prohibit the implicit and ROPC grants for new deployments, mandate refresh-token rotation with theft detection, prefer sender-constrained tokens for high-risk APIs, and bind to OAuth 2.1 for the underlying framework.

A profile that delegates authorization without binding to RFC 9700 is non-conformant.

## Implementation Notes

- PKCE is not optional in any RFC 9700-conformant deployment; the `plain` code-challenge method is deprecated.
- Refresh-token rotation with theft detection uses a reuse-detection signal; a reused refresh token must trigger client-wide revocation.
- Audience restriction on access tokens prevents token misuse across relying parties.
- The implicit grant is removed because of referrer-header leakage, browser-history leakage, and inability to bind tokens to clients.
- The ROPC grant is removed because it requires the client to handle user credentials directly.
- Mixed deployments that still use the implicit or ROPC grant should treat those grants as migration targets with deadlines.

## Companion Documents

- [IETF OAuth 2.1 Authorization Framework](IETF_OAUTH_2_1_AUTHORIZATION_FRAMEWORK.md)
- [OpenID Connect Core 1.0](OPENID_CONNECT_CORE_1_0.md)
- [FAPI 2.0 Security Profile](FAPI_2_0_SECURITY_PROFILE.md)
- [Token Storage Best Practices](TOKEN_STORAGE_BEST_PRACTICES.md)
- [NIST SP 800-63 Digital Identity Governance](../standards/NIST_SP_800_63_DIGITAL_IDENTITY_GOVERNANCE.md)
