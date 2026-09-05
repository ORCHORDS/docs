---
title: "OpenID Connect Core 1.0 Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "OpenID Foundation; https://openid.net/specs/openid-connect-core-1_0.html"
---

# OpenID Connect Core 1.0 Reference Card

## Scope

Reference card for OpenID Connect Core 1.0, an identity layer built on top of OAuth 2.0 that adds ID Tokens (signed JWTs), the userinfo endpoint, and standard claims for authentication. Profiles that govern federated authentication, social login, or single sign-on (SSO) should cite OpenID Connect Core 1.0 and bind to OAuth 2.1, RFC 9700, FAPI 2.0, NIST SP 800-63, and the token storage guidance.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | OpenID Connect Core 1.0 (final, OpenID Foundation) |
| Status | Final specification, errata tracked |
| Companion artifacts | OAuth 2.1, RFC 9700, FAPI 2.0, OpenID Connect Discovery 1.0, OpenID Connect Dynamic Client Registration 1.0 |
| Source URL | https://openid.net/specs/openid-connect-core-1_0.html |

## Plan

1. Reference OpenID Connect Core 1.0 by current errata whenever a profile governs federated authentication.
2. Use the authorization-code flow with PKCE; the implicit flow is discouraged.
3. Validate the ID Token signature, issuer (`iss`), audience (`aud`), nonce (`nonce`), and expiry (`exp`).
4. Use the userinfo endpoint for retrieving current claims; do not rely solely on the ID Token for user attributes.
5. Apply pairwise subject identifiers (PPID) when correlation across relying parties is undesirable.
6. Bind to OAuth 2.1, RFC 9700, and FAPI 2.0 for the authorization and security treatment.
7. Bind to NIST SP 800-63 for the identity assurance level (IAL) and authenticator assurance level (AAL).
8. Document ID Token lifetimes, refresh-token rotation, and sender-constrained token strategy.
9. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- OpenID Connect Core 1.0 specification (current errata).
- OpenID Provider (OP) metadata, JWKS endpoint, registration policy.
- Relying Party (RP) client registration, redirect URI list, scope set.
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats OpenID Connect Core 1.0 as the canonical reference for delegated authentication. Profiles that delegate authentication should cite OpenID Connect Core 1.0 by errata, mandate ID Token validation (signature, issuer, audience, nonce, expiry), bind to OAuth 2.1 for authorization, bind to NIST SP 800-63 for assurance levels, and bind to RFC 9700 for the security treatment.

A profile that delegates authentication without binding to OpenID Connect Core 1.0, OAuth 2.1, and NIST SP 800-63 is non-conformant.

## Implementation Notes

- The `nonce` parameter is required for the authorization-code flow to prevent replay.
- The `at_hash` and `c_hash` parameters in the ID Token bind the access token and authorization code to the ID Token.
- Use the Discovery endpoint (RFC-defined OpenID Connect Discovery 1.0) for runtime metadata retrieval.
- Pairwise subject identifiers prevent correlation by a malicious relying party.
- ID Tokens are short-lived; do not use ID Tokens as access tokens.
- The userinfo response should be validated against the ID Token claims to detect token substitution.

## Companion Documents

- [IETF OAuth 2.1 Authorization Framework](IETF_OAUTH_2_1_AUTHORIZATION_FRAMEWORK.md)
- [FAPI 2.0 Security Profile](FAPI_2_0_SECURITY_PROFILE.md)
- [IETF RFC 9700 OAuth 2.0 Security BCP](IETF_RFC_9700_OAUTH_2_0_SECURITY_BCP.md)
- [Token Storage Best Practices](TOKEN_STORAGE_BEST_PRACTICES.md)
- [NIST SP 800-63 Digital Identity Governance](../standards/NIST_SP_800_63_DIGITAL_IDENTITY_GOVERNANCE.md)
- [ISO/IEC 29115 Entity Authentication Assurance Governance](../standards/ISO_IEC_29115_ENTITY_AUTH_ASSURANCE_GOVERNANCE.md)
