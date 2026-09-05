---
title: "FAPI 2.0 Security Profile Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "OpenID Foundation FAPI Working Group; https://openid.net/specs/fapi-2_0-security-profile.html"
---

# FAPI 2.0 Security Profile Reference Card

## Scope

Reference card for the Financial-grade API (FAPI) 2.0 Security Profile, an OpenID Foundation specification that defines the security requirements for APIs that handle high-risk, regulated, or financial data. FAPI 2.0 mandates sender-constrained tokens (mTLS or DPoP), PKCE for all clients, JAR (RFC 9101), JARM (RFC 9027), and a strict redirect URI match. Profiles that govern open banking, PSD2, healthcare, or any regulated API access should cite FAPI 2.0 and bind to OAuth 2.1, OpenID Connect Core 1.0, RFC 9700, and NIST SP 800-63.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | FAPI 2.0 Security Profile (final, OpenID Foundation) |
| Status | Final specification |
| Companion artifacts | OAuth 2.1, OpenID Connect Core 1.0, RFC 9700, RFC 8705 (mTLS), RFC 9449 (DPoP), RFC 9101 (JAR), RFC 9027 (JARM) |
| Source URL | https://openid.net/specs/fapi-2_0-security-profile.html |

## Plan

1. Reference FAPI 2.0 by current revision whenever a profile governs a regulated or financial API.
2. Mandate sender-constrained tokens (mTLS via RFC 8705 or DPoP via RFC 9449) for every client.
3. Mandate PKCE (RFC 7636) for every client including confidential clients.
4. Mandate JAR (RFC 9101) for signed authorization requests where authorization-server support is available.
5. Mandate JARM (RFC 9027) for signed authorization responses where authorization-server support is available.
6. Require exact redirect URI match on every authorization request.
7. Require ID Token validation per OpenID Connect Core 1.0.
8. Bind to OAuth 2.1, OpenID Connect Core 1.0, and RFC 9700 for the underlying authorization, authentication, and security treatment.
9. Bind to NIST SP 800-63 for the identity assurance level (IAL) and authenticator assurance level (AAL).
10. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- FAPI 2.0 Security Profile specification.
- Authorization-server FAPI conformance attestation.
- Client registration policy: sender-constrained token requirement, redirect URI exact-match enforcement, scope definitions.
- Risk-management framework (NIST CSF, ISO 27001, PCI DSS) and the threat model.

## ORCHORDS Profile

ORCHORDS treats FAPI 2.0 as the canonical reference for high-risk API authorization. Profiles that govern regulated APIs should cite FAPI 2.0 by revision, mandate sender-constrained tokens (mTLS or DPoP), mandate PKCE for all clients, mandate JAR/JARM where supported, bind to OAuth 2.1 for the underlying authorization, bind to OpenID Connect Core 1.0 when authentication is delegated, and bind to NIST SP 800-63 for assurance levels.

A profile that governs a regulated API without binding to FAPI 2.0 is non-conformant.

## Implementation Notes

- mTLS client authentication (RFC 8705) and DPoP (RFC 9449) are the two FAPI-recognized sender-constrained mechanisms.
- JAR (RFC 9101) protects request integrity; JARM (RFC 9027) protects response integrity.
- The authorization-server must publish a FAPI conformance statement that identifies the supported sender-constrained token mechanism.
- Confidential clients must hold a PKI certificate for mTLS or a DPoP key for DPoP; the key must be rotated per the FAPI policy.
- The redirect URI must match exactly; wildcards are not permitted under FAPI 2.0.
- ID Token and access token validation must follow OpenID Connect Core 1.0 and RFC 9700.

## Companion Documents

- [IETF OAuth 2.1 Authorization Framework](IETF_OAUTH_2_1_AUTHORIZATION_FRAMEWORK.md)
- [OpenID Connect Core 1.0](OPENID_CONNECT_CORE_1_0.md)
- [IETF RFC 9700 OAuth 2.0 Security BCP](IETF_RFC_9700_OAUTH_2_0_SECURITY_BCP.md)
- [Token Storage Best Practices](TOKEN_STORAGE_BEST_PRACTICES.md)
- [NIST SP 800-63 Digital Identity Governance](../standards/NIST_SP_800_63_DIGITAL_IDENTITY_GOVERNANCE.md)
