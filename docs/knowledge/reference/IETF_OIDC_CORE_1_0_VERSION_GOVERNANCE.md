---
title: "OpenID Connect Core 1.0 Version Governance"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "OpenID Foundation, OpenID Connect Core 1.0; https://openid.net/specs/openid-connect-core-1_0.html"
---

# OpenID Connect Core 1.0 Version Governance

## Scope

Reference card for OpenID Connect Core 1.0, the identity layer on top of OAuth 2.0 (RFC 6749 / RFC 6750). Used by platform, security, and operations teams when documenting identity federation, RP/OP posture, ID Token validation, userinfo, or session management. Treats OpenID Connect Core 1.0 as the authoritative identity spec, with OAuth 2.0 (RFC 6749), OAuth 2.1 (draft-ietf-oauth-v2-1), OAuth 2.0 for Browser-Based Apps (RFC 8252), OAuth 2.0 Security BCP (RFC 9700), JWT (RFC 7519), JWS (RFC 7515), PKCE (RFC 7636), PAR (RFC 9126), RAR (RFC 9396), JWKS (RFC 7517), DPoP (RFC 9449), and the OIDC discovery, dynamic registration, session management, front-channel logout, back-channel logout, and RP-initiated logout specifications as companion documents.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | OpenID Connect Core 1.0 |
| Status | Final (OIDC Foundation) |
| Authentication request | response_type (code, id_token, id_token+token); scope (openid required); nonce; state; PKCE (RFC 7636) |
| Tokens | ID Token (JWT/JWS, RFC 7519 / RFC 7515), Access Token (RFC 6750), Refresh Token |
| Claims | iss, sub, aud, exp, iat, nbf, auth_time, acr, amr, nonce, at_hash, c_hash |
| Discovery | /.well-known/openid-configuration |
| JWKS | jwks_uri (RFC 7517) |
| Verification source | https://openid.net/specs/openid-connect-core-1_0.html |

## Plan

1. Identify the deployment context (RP — web/native/SPA, OP — first-party or third-party identity provider, broker).
2. Map required behaviour against OIDC Core 1.0 § 2–§ 15 (flows, ID Token validation, userinfo, session management, logout).
3. Capture operational requirements: discovery handling, JWKS rotation, PKCE (RFC 7636), PAR (RFC 9126), DPoP (RFC 9449), token introspection / userinfo handling, and BCP posture (RFC 9700).
4. Validate against the live OIDC provider metadata and IANA OAuth / OIDC registries.

## Inputs

- Client type (web / native / SPA / device) and the matching OAuth profile (RFC 8252 for browser-based apps).
- Allowed response types and grant types (e.g., authorization_code, refresh_token, urn:ietf:params:oauth:grant-type:device_code per RFC 8628, urn:ietf:params:oauth:grant-type:token-exchange per RFC 8693).
- Token lifetimes, refresh policy, sender-constrained posture (DPoP, RFC 9449, or MTLS RFC 8705).
- Logout profile (front-channel per OIDC Front-Channel Logout 1.0, back-channel per OIDC Back-Channel Logout 1.0, or RP-initiated per OIDC RP-Initiated Logout 1.0).
- Federation posture (OIDC Federation 1.0 if applicable).

## ORCHORDS Profile

This guide is used as a reference when reviewing identity-federation documentation or designing RP/OP posture. It does NOT introduce protocol behaviour beyond what the OIDC, OAuth, JWT, and IETF specifications specify. When a behavioural rule that is not captured here is required by an OIDC operation, escalate to a fresh review against the current OIDC and IETF specifications.

## Implementation Notes

- Always use authorization_code with PKCE (RFC 7636); never use implicit grant (response_type=token) for new deployments per RFC 9700.
- For SPAs, follow RFC 8252 (Authorization Code with PKCE using backend-for-frontend); never store tokens in localStorage for high-privilege APIs.
- Validate ID Token signature, issuer (iss), audience (aud), nonce, auth_time, and acr per OIDC Core 1.0 § 3.1.3.7.
- Use PAR (RFC 9126) for sensitive RPs to lock down request parameters; pair with RAR (RFC 9396) for fine-grained authorisation requests.
- Use sender-constrained tokens (DPoP per RFC 9449, MTLS per RFC 8705) for high-value APIs.
- Treat OIDC Discovery /.well-known/openid-configuration as the canonical source of truth; refresh JWKS cache on key rotation event.
- For logout, prefer back-channel logout (OIDC Back-Channel Logout 1.0) for confidential clients; use front-channel logout only where the RP can verify an ID Token hint.

## Companion Documents

- RFC 6749 (OAuth 2.0)
- RFC 6750 (OAuth 2.0 Bearer Token Usage)
- RFC 7515 (JWS) / RFC 7517 (JWKS) / RFC 7519 (JWT)
- RFC 7636 (PKCE)
- RFC 8252 (OAuth for Browser-Based Apps)
- RFC 8628 (Device Grant)
- RFC 8693 (Token Exchange)
- RFC 8705 (OAuth 2.0 Mutual TLS)
- RFC 9126 (PAR)
- RFC 9396 (RAR)
- RFC 9449 (DPoP)
- RFC 9700 (OAuth 2.0 Security BCP)
- OIDC Discovery 1.0 / Dynamic Registration 1.0 / Session Management 1.0 / Front-Channel Logout 1.0 / Back-Channel Logout 1.0 / RP-Initiated Logout 1.0 / Federation 1.0
