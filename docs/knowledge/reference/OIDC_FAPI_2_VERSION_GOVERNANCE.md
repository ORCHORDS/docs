---
title: "OpenID Connect FAPI 2.0 Profile Version Governance"
owner: "Knowledge Engineering"
status: "approved"
classification: "public"
last-reviewed: "2026-09-08"
review-cycle: "180 days"
next-review: "2027-03-07"
source: "OpenID Foundation FAPI Working Group specifications and Open Banking profile mandates"
---

# OpenID Connect FAPI 2.0 Profile Version Governance

## Scope and Baseline

The Financial-grade API (FAPI) profile layers mandatory controls on top of OpenID Connect Core 1.0 and OAuth 2.0 to deliver interoperable, regulator-aligned security for high-risk APIs. FAPI inherits OIDC Core 1.0 as its identity layer and constrains authorization server metadata, client behavior, and token semantics so deployments satisfy financial regulators. Where OIDC Core leaves a feature optional, FAPI promotes it to mandatory.

## Profile Variants

FAPI 1.0 Advanced ships in two modes: Read-Only API, suitable for data retrieval, and Read-Write API, which adds transaction submission and stricter request integrity. FAPI 2.0 supersedes both and publishes two companion specifications: the FAPI 2.0 Security Profile, which defines baseline authorization and token binding, and FAPI 2.0 Message Signing, which standardizes JWS request and response object signing. Implementers should target FAPI 2.0 unless an authority mandates FAPI 1.0 Advanced explicitly.

## Mandated Mechanisms

FAPI requires PKCE on every authorization request, including confidential clients. JWT-secured Authorization Response Mode (JARM) replaces redirect-query responses with signed JWTs to prevent tampering. Pushed Authorization Requests (PAR, RFC 9126) move the authorization request payload through the back channel, removing sensitive parameters from the front channel.

## Client Authentication

Allowed confidential client methods are restricted to asymmetric or certificate-bound options: `private_key_jwt` and `tls_client_auth`. Shared-secret `client_secret_basic` and `client_secret_post` are disallowed under FAPI 2.0.

## Sender-Constrained Tokens

FAPI 2.0 mandates sender-constrained access tokens. Implementations choose DPoP (RFC 9449) for application-layer proof of possession or mTLS (RFC 8705) for transport-layer binding. Token replay outside the bound channel is rejected by the resource server.

## Signed Objects

Authorization request objects and response objects are JWTs signed per JWS requirements, formalized in RFC 9901. Both client and authorization server validate signature, issuer, audience, and freshness before acting.

## Discovery and Metadata

Authorization servers publish `.well-known/openid-configuration` enriched with FAPI-specific metadata: supported response modes, token endpoint auth methods, signing algorithms, and PAR requirements. Clients refuse non-conformant metadata.

## Sector Applicability

FAPI governs open banking APIs in the UK, Brazil, Saudi Arabia, and Australia, and underpins open finance, healthcare data exchange, and insurance data-sharing regimes. The forthcoming EU PSD3 references FAPI 2.0 as the technical baseline for strong customer authentication interfaces.

## Conformance and Certification

The OpenID Foundation runs the FAPI Conformance Suite and grants certification badges per profile. Certification is the primary procurement signal in regulated markets.

## Compatibility

FAPI 2.0 is compatible with OIDC Core 1.0 and tracks OAuth 2.1 security recommendations.

## Compatibility Horizon

FAPI 2.0 is the strategic target through 2027. FAPI 1.0 Advanced remains supported for legacy ecosystems but receives only defect fixes. Track RFC 9901 and the Foundation roadmap for forward migrations.

## Version Selection Decision Tree

Choose Read-Only versus Read-Write based on whether the client submits transactions. Pick mTLS when existing PKI and hardware modules are available; pick DPoP for mobile and cross-platform deployments without mTLS. Select the FAPI 2.0 Message Signing profile unless a regulator pins to FAPI 1.0 Advanced JWS.

## Operational Impact

Deployments must rotate signing keys, monitor PAR latency, and validate sender-constrained tokens at the resource server. Certificate and DPoP key lifecycle management become primary operational duties.

## Cross-references

- See `docs/knowledge/reference/OIDC_CORE_VERSION_GOVERNANCE.md:1` for the OIDC Core baseline.
- See `docs/knowledge/reference/OAUTH_21_VERSION_GOVERNANCE.md:1` for OAuth 2.1 alignment.
- See `docs/knowledge/reference/PSD3_EU_VERSION_GOVERNANCE.md:1` for PSD3 mapping.
- See `docs/knowledge/reference/OPEN_BANKING_PROFILES.md:1` for jurisdictional mandates.

## Footer

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.