---
title: OAuth 2.1 Authorization Framework Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: IETF OAuth 2.1 draft (draft-ietf-oauth-v2-1-13, July 2025); OAuth 2.0 Authorization Framework (RFC 6749, October 2012); Bearer Token Usage (RFC 6750, October 2012); OAuth 2.0 Threat Model (RFC 6819); OAuth 2.0 Security Best Current Practice (RFC 9700, January 2025); https://datatracker.ietf.org/doc/draft-ietf-oauth-v2-1/
---

# OAuth 2.1 Authorization Framework Version Governance

## Scope

This card governs how `orchords-docs` evaluates OAuth 2.1 — the consolidation of OAuth 2.0 (RFC 6749) with its security BCP (RFC 9700) and PKCE (RFC 7636) — as the delegated-authorization protocol for reference architectures. It is the reference input for any card that mints, validates, or proxies access tokens.

## Why this card exists

OAuth 2.1 is a consolidation draft: it does not add new features; it removes features that have been deprecated in RFC 9700 (the OAuth 2.0 Security Best Current Practice). Treating "OAuth" as versionless produces reference architectures that include deprecated flows (Implicit, ROPC) and accept insecure redirect URIs.

## Document set

- **draft-ietf-oauth-v2-1** — current consolidation (latest revision at time of writing: -13, July 2025).
- **RFC 6749** — OAuth 2.0 Authorization Framework.
- **RFC 6750** — Bearer Token Usage.
- **RFC 6819** — OAuth 2.0 Threat Model.
- **RFC 7636** — PKCE.
- **RFC 7662** — Token Introspection.
- **RFC 7009** — Token Revocation.
- **RFC 7591** — Dynamic Client Registration.
- **RFC 7592** — Dynamic Client Registration Management.
- **RFC 8252** — OAuth 2.0 for Native Apps.
- **RFC 8628** — Device Authorization Grant.
- **RFC 9068** — JWT Access Token Profile.
- **RFC 9126** — Pushed Authorization Requests (PAR).
- **RFC 9101** — JWT-secured Authorization Requests (JAR).
- **RFC 9207** — Authorization Server Issuer Identification.
- **RFC 9700** — OAuth 2.0 Security Best Current Practice (BCP).

References: `https://datatracker.ietf.org/doc/draft-ietf-oauth-v2-1/`.

## Grant types — supported matrix

| Grant type | OAuth 2.1 status | Use case |
|---|---|---|
| `authorization_code` | required | default for user-facing clients |
| `authorization_code` + PKCE (RFC 7636) | required | default for every new public client |
| `client_credentials` | required | machine-to-machine |
| `refresh_token` | required | rotating tokens |
| `urn:ietf:params:oauth:grant-type:device_code` | required | input-constrained devices |
| `urn:openid:params:grant-type:ciba` | optional | decoupled authentication |
| Implicit (`response_type=token`) | **removed** | n/a |
| ROPC (`grant_type=password`) | **removed** | n/a |

References: `draft-ietf-oauth-v2-1-13` § 2.

## Client types

| Type | Authentication | Notes |
|---|---|---|
| `public` (e.g., SPA, native app) | none (PKCE required) | uses PKCE; never `client_secret` |
| `confidential` (e.g., backend service) | `client_secret_basic`, `client_secret_post`, `private_key_jwt`, `tls_client_auth` | uses confidential client credentials |

## Client authentication methods

| Method | Use case | Notes |
|---|---|---|
| `client_secret_basic` | legacy confidential | require TLS; rotate secret per `SECRET_ROTATION_PLAYBOOK.md` |
| `client_secret_post` | legacy confidential | require TLS; rotate secret per playbook |
| `private_key_jwt` | FAPI 2.0, FAPI 1.0 Advanced | preferred for new confidential clients |
| `tls_client_auth` | FAPI 2.0 | preferred for service-to-service |
| `none` | public client | PKCE is the binding security; client_secret must not be used |

## Access token formats

| Format | Use case | Notes |
|---|---|---|
| Opaque token | legacy | validated via token introspection (RFC 7662) |
| JWT access token | modern | RFC 9068 profile preferred; bind to issuer |

References: `https://www.rfc-editor.org/rfc/rfc9068.html`.

## Authorization endpoint hardening (RFC 9700 BCP)

- `state` parameter is required for every authorization request.
- PKCE is required for every authorization code flow (public and confidential).
- Exact redirect URI matching is required (no prefix matching, no path-parameter matching).
- `iss` parameter in authorization response (RFC 9207) is required for every request.
- `response_mode=query` is forbidden when response contains tokens.
- `response_mode=fragment` is forbidden for Authorization Code Flow.
- `response_mode=web_message` is forbidden for same-origin clients.

## Token endpoint hardening

- `client_secret_basic` over TLS 1.2+ only.
- PKCE code verifier validated server-side on every authorization code exchange.
- Refresh token rotation: every refresh issues a new refresh token and invalidates the old one (RFC 9700 § 4.14).
- Refresh token reuse detection invalidates the entire refresh-token family.
- Sender-constrained tokens (DPoP RFC 9449, MTLS RFC 8705) for high-security flows.

## Token revocation

- RFC 7009 revocation endpoint is exposed for every token type.
- Revocation is idempotent (success even if the token was already revoked).
- Refresh tokens and access tokens are revoked independently.

## Pushed Authorization Requests (PAR)

PAR (RFC 9126) is the BCP-recommended way to send authorization requests for high-security flows. Policy:

- PAR is required for FAPI 2.0 clients.
- PAR is allowed but optional for non-FAPI clients.
- The `request_uri` returned by PAR is single-use and ≤ 60 seconds TTL.

## JWT-secured Authorization Requests (JAR)

JAR (RFC 9101) signs the request object with the client's key. Policy:

- JAR is required for FAPI 2.0.
- JAR is allowed but optional elsewhere.
- The signed request object includes `iss`, `aud`, `iat`, `exp`, `jti`.

## Mandatory pre-flight (before adopting a new OAuth 2.0/2.1 AS)

1. AS supports PKCE (RFC 7636) with `S256`.
2. AS supports exact redirect URI matching.
3. AS supports RFC 9207 `iss` parameter.
4. AS supports RFC 9700 BCP.
5. AS exposes a token introspection endpoint (RFC 7662) if opaque tokens are used.
6. AS supports RFC 7009 token revocation.
7. AS supports confidential client authentication per the policy table.

## Sources

- draft-ietf-oauth-v2-1-13: `https://datatracker.ietf.org/doc/draft-ietf-oauth-v2-1/`
- RFC 6749 (OAuth 2.0 Framework): `https://www.rfc-editor.org/rfc/rfc6749`
- RFC 6750 (Bearer Token Usage): `https://www.rfc-editor.org/rfc/rfc6750`
- RFC 6819 (Threat Model): `https://www.rfc-editor.org/rfc/rfc6819`
- RFC 7636 (PKCE): `https://www.rfc-editor.org/rfc/rfc7636`
- RFC 7662 (Token Introspection): `https://www.rfc-editor.org/rfc/rfc7662`
- RFC 7009 (Token Revocation): `https://www.rfc-editor.org/rfc/rfc7009`
- RFC 8628 (Device Authorization Grant): `https://www.rfc-editor.org/rfc/rfc8628`
- RFC 8252 (Native Apps): `https://www.rfc-editor.org/rfc/rfc8252`
- RFC 9068 (JWT Access Token Profile): `https://www.rfc-editor.org/rfc/rfc9068`
- RFC 9126 (PAR): `https://www.rfc-editor.org/rfc/rfc9126`
- RFC 9101 (JAR): `https://www.rfc-editor.org/rfc/rfc9101`
- RFC 9207 (Issuer Identification): `https://www.rfc-editor.org/rfc/rfc9207`
- RFC 9700 (OAuth Security BCP): `https://www.rfc-editor.org/rfc/rfc9700`
