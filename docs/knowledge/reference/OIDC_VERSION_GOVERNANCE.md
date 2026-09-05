---
title: OpenID Connect (OIDC) Version Governance (OASIS, FAPI, FAPI 2.0)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: OpenID Connect Core 1.0 (November 2014); OpenID Connect Discovery 1.0; OpenID Connect Session Management 1.0; FAPI 1.0 Baseline and Advanced; FAPI 2.0 Security Profile; OpenID for Verifiable Credentials (OIDC4VC); https://openid.net/connect/
---

# OpenID Connect (OIDC) Version Governance (OASIS, FAPI, FAPI 2.0)

## Scope

This card governs how `orchords-docs` evaluates OpenID Connect (OIDC) as an identity federation protocol. It is the reference input for any SSO integration card, any API gateway that accepts bearer tokens, and any verifiable-credential integration.

## Why this card exists

OIDC is layered on top of OAuth 2.0 (RFC 6749, RFC 6750). It introduces an ID Token (JWT) signed by the OP, a UserInfo endpoint for claims, and a discovery document. Operational pain comes from (a) confusion between OIDC (federated identity) and OAuth 2.0 (delegated authorization), (b) acceptance of unsigned ID Tokens, and (c) misuse of the implicit flow.

## Document set

- **OpenID Connect Core 1.0** (Nov 2014) — ID Token, UserInfo, flows, claims.
- **OpenID Connect Discovery 1.0** (Nov 2014) — `.well-known/openid-configuration` discovery document.
- **OpenID Connect Session Management 1.0** (Nov 2014) — browser-based session, front-channel logout, back-channel logout.
- **OpenID Connect Dynamic Client Registration 1.0** (Nov 2014) — registering clients with the OP.
- **OpenID for Verifiable Credential Issuance (OIDC4VCI)** (2024) — issuing verifiable credentials.
- **OpenID for Verifiable Presentations (OIDC4VP)** (2024) — presenting verifiable credentials.
- **FAPI 1.0 Baseline** (March 2021) — financial-grade API security profile.
- **FAPI 1.0 Advanced** (March 2021) — adds signed requests and encrypted responses.
- **FAPI 2.0 Security Profile** (October 2023) — consolidates FAPI 1.0 requirements.
- **FAPI 2.0 Message Signing** (October 2023) — JARM, JAR, JOSE signing.

References: `https://openid.net/connect/`, `https://openid.net/specs/openid-connect-core-1_0.html`.

## Flow support matrix

| Flow | Use case | Notes |
|---|---|---|
| Authorization Code Flow with PKCE | default | RFC 7636 mandatory |
| Authorization Code Flow (no PKCE) | legacy | forbidden for new integrations |
| Implicit Flow | deprecated | forbidden for new integrations |
| Hybrid Flow | high-security | allowed for FAPI 2.0 only |
| Client Credentials | machine-to-machine | allowed |
| Resource Owner Password Credentials | deprecated | forbidden for new integrations |
| Refresh Token Rotation | standard | required for confidential clients |
| Device Authorization Flow | input-constrained devices | RFC 8628 |
| CIBA (Client Initiated Backchannel Authentication) | decoupled auth | OIDC CIBA profile |

References: `https://openid.net/specs/openid-connect-core-1_0.html`, `https://openid.net/specs/openid-client-initiated-backchannel-authentication-core-1_0.html`.

## ID Token policy

The ID Token is a JWT. Required claims:

| Claim | Required |
|---|---|
| `iss` | yes |
| `sub` | yes |
| `aud` | yes |
| `exp` | yes |
| `iat` | yes |
| `nonce` | yes for browser-based flows |
| `auth_time` | yes for `max_age` enforcement |
| `acr` | yes when `RequestAuthnContext` was set |
| `amr` | optional |

Signature algorithm policy:

- `PS256` (RSA-PSS) preferred.
- `ES256` (ECDSA P-256) preferred for new deployments.
- `RS256` acceptable.
- `RS1`, `ES1`, `none` forbidden.

## Discovery document

The project's reference integration always pulls the discovery document from `${ISSUER}/.well-known/openid-configuration`. The discovery document must include:

- `issuer`
- `authorization_endpoint`
- `token_endpoint`
- `jwks_uri`
- `userinfo_endpoint`
- `end_session_endpoint`
- `response_types_supported`
- `subject_types_supported`
- `id_token_signing_alg_values_supported`
- `token_endpoint_auth_methods_supported`
- `code_challenge_methods_supported` (must include `S256`)

The integration **must** verify `iss` from the discovery document matches the `iss` claim of every ID Token.

## JWKs policy

The project's JWKS endpoint must publish all public signing keys used by the OP. The integration must:

- Cache the JWKS for ≤ 5 minutes.
- Rotate the cache when an unknown `kid` is encountered.
- Reject any token whose `kid` is not in the JWKS.
- Reject any token whose signature does not validate against the published key.

## PKCE policy

PKCE (RFC 7636) is mandatory for every Authorization Code Flow. Policy:

- `code_challenge_method = S256` only. `plain` is forbidden.
- `code_verifier` length: 43 — 128 characters, base64url-encoded without padding.
- `code_challenge` is the SHA-256 of the `code_verifier`, base64url-encoded.

## FAPI 2.0 (high-security profile)

When a reference architecture targets FAPI 2.0 conformance, the integration must:

- Use `private_key_jwt` or `tls_client_auth` for client authentication.
- Sign request objects (JAR — RFC 9101).
- Sign response objects (JARM) when the OP supports it.
- Use PAR (Pushed Authorization Requests, RFC 9126) for every authorization request.
- Reject any request without `iss` claim when using JAR.

References: `https://openid.net/specs/fapi-2_0-security-profile.html`.

## OIDC4VC / OIDC4VP

The project adopts OpenID for Verifiable Credential Issuance (OIDC4VCI) and OpenID for Verifiable Presentations (OIDC4VP) only when verifiable-credential use cases are explicitly cited in the change ticket. The reference card must enumerate:

- Credential format (`jwt_vc`, `ldp_vc`, `mso_mdoc`).
- Cryptographic suite (`ES256`, `EdDSA`).
- Issuer DID method (`did:web`, `did:key`, `did:jwk`).
- Trust framework (`GAIA-X`, `EBSI`, etc.).

References: `https://openid.net/specs/openid-4-verifiable-credential-issuance-1_0.html`, `https://openid.net/specs/openid-4-verifiable-presentations-1_0.html`.

## Mandatory pre-flight (before adopting a new OIDC OP)

1. OP publishes a discovery document with all required fields.
2. OP publishes a JWKS document with a current signing key.
3. OP supports PKCE with `S256`.
4. OP supports the desired flows.
5. OP supports `private_key_jwt` or `tls_client_auth` (for FAPI 2.0).
6. OP supports PAR (for FAPI 2.0).

## Sources

- OpenID Connect Core 1.0: `https://openid.net/specs/openid-connect-core-1_0.html`
- OpenID Connect Discovery 1.0: `https://openid.net/specs/openid-connect-discovery-1_0.html`
- OpenID Connect Session Management 1.0: `https://openid.net/specs/openid-connect-session-1_0.html`
- FAPI 2.0 Security Profile: `https://openid.net/specs/fapi-2_0-security-profile.html`
- RFC 7636 (PKCE): `https://www.rfc-editor.org/rfc/rfc7636`
- RFC 9126 (PAR): `https://www.rfc-editor.org/rfc/rfc9126`
- RFC 9101 (JAR): `https://www.rfc-editor.org/rfc/rfc9101`
