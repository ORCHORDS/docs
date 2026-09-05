---
title: "IETF OAuth 2.1 Authorization Framework Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF OAuth Working Group draft-ietf-oauth-v2-1 (current); https://datatracker.ietf.org/doc/draft-ietf-oauth-v2-1/"
---

# IETF OAuth 2.1 Authorization Framework Reference Card

## Scope

Reference card for the IETF OAuth 2.1 Authorization Framework, which consolidates OAuth 2.0 (RFC 6749) and OAuth 2.0 for Browser-Based Apps (RFC 8252) into a single specification, removes insecure deprecated flows (the implicit grant and the resource-owner password credentials grant), and mandates PKCE (RFC 7636) for all clients. Profiles that govern delegated authorization, third-party API access, or single-page application authorization should cite OAuth 2.1 and bind to FAPI 2.0, OpenID Connect Core 1.0, RFC 9700, and the OAuth 2.0 token storage guidance.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | IETF draft-ietf-oauth-v2-1 (current revision in IETF review) |
| Status | Internet-Draft, intended to obsolete parts of RFC 6749 and RFC 8252 |
| Companion artifacts | RFC 6749, RFC 8252, RFC 7636, RFC 9700, OpenID Connect Core 1.0, FAPI 2.0 |
| Source URL | https://datatracker.ietf.org/doc/draft-ietf-oauth-v2-1/ |

## Plan

1. Reference OAuth 2.1 by current revision whenever a profile governs delegated authorization.
2. Require PKCE on every client, including confidential clients; PKCE is not optional in OAuth 2.1.
3. Forbid the implicit grant; treat any existing use as a migration target.
4. Forbid the resource-owner password credentials (ROPC) grant for new deployments; document exceptions with approver, scope, expiration, and compensating controls.
5. Use the authorization-code flow with PKCE for native, single-page, and traditional web clients.
6. Bind to RFC 9700 (OAuth 2.0 Security Best Current Practice) for the security treatment.
7. Bind to FAPI 2.0 when the client is a high-risk financial or regulated API consumer.
8. Bind to OpenID Connect Core 1.0 when authentication is also delegated.
9. Document token lifetimes, refresh-token rotation policy, and sender-constrained token strategy.
10. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- OAuth 2.1 draft (current revision).
- Authorization-server policy: client registration, scope definitions, redirect URI registration, token lifetimes, PKCE requirement.
- Client inventory with confidential vs public classification, redirect URI list, and scope usage.
- Risk-management framework (NIST CSF, ISO 27001 Annex A.5.15/A.8.2/A.8.3) and the threat model.

## ORCHORDS Profile

ORCHORDS treats OAuth 2.1 as the canonical reference for delegated authorization. Profiles that delegate authorization should cite OAuth 2.1 by revision, mandate PKCE for all clients, prohibit the implicit and ROPC grants for new deployments, bind to RFC 9700 for security, bind to FAPI 2.0 for regulated APIs, and bind to OpenID Connect Core 1.0 when authentication is delegated in parallel.

A profile that delegates authorization without binding to OAuth 2.1, RFC 9700, and (where applicable) FAPI 2.0 is non-conformant.

## Implementation Notes

- The implicit grant is removed because access tokens cannot be refreshed, can leak via referrer headers and browser history, and cannot be sender-constrained.
- The ROPC grant is removed because it requires the client to handle user credentials directly, violating the delegation principle.
- PKCE protects against authorization-code interception; the S256 code-challenge method is required for confidential clients.
- Refresh-token rotation with sender-constrained tokens (DPoP, RFC 9449) or mTLS (RFC 8705) is recommended.
- Authorization-server metadata (RFC 8414) and dynamic client registration should be used where deployment scope permits.
- OAuth 2.1 is not yet an RFC; profiles should track the current draft revision and document the revision date.

## Companion Documents

- [FAPI 2.0 Security Profile](FAPI_2_0_SECURITY_PROFILE.md)
- [OpenID Connect Core 1.0](OPENID_CONNECT_CORE_1_0.md)
- [IETF RFC 9700 OAuth 2.0 Security BCP](IETF_RFC_9700_OAUTH_2_0_SECURITY_BCP.md)
- [Token Storage Best Practices](TOKEN_STORAGE_BEST_PRACTICES.md)
- [NIST SP 800-63 Digital Identity Governance](../standards/NIST_SP_800_63_DIGITAL_IDENTITY_GOVERNANCE.md)
- [ISO/IEC 29115 Entity Authentication Assurance Governance](../standards/ISO_IEC_29115_ENTITY_AUTH_ASSURANCE_GOVERNANCE.md)
