---
title: "Rich Authorization Requests Version Governance (RFC 9396)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 9396; https://www.rfc-editor.org/rfc/rfc9396"
---

# Rich Authorization Requests Version Governance (RFC 9396)

## Scope

Reference card for Rich Authorization Requests (RAR) as defined by IETF RFC 9396. Used by identity, API, and platform teams when documenting OAuth 2.0 authorisation requests beyond coarse-grained scopes, fine-grained resource-authorisation decisions, or RAR-aligned token issue/consume. Treats RFC 9396 as the authoritative RAR extension, with RFC 6749 / RFC 6750 (OAuth 2.0 base), RFC 9126 (PAR), RFC 8414 (Authorization Server Metadata), RFC 8705 (mTLS client auth), RFC 9449 (DPoP), RFC 9700 (OAuth 2.0 Security BCP), draft-ietf-authzen-gnap-rar-profile (RAR-GNAP alignment), and the OIDC RAR profile work as companion references.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 9396, "Rich Authorization Requests for OAuth 2.0" |
| Status | Proposed Standard |
| Authorization Request parameter | `authorization_details` (top-level JSON array) |
| Element types | `"type"` discriminator; access / identity / bad-rendering / bad-encoder / sub-issued / resource_action etc. (registered types listed in RFC 9396 § 4.1 and updates) |
| Companion | RFC 9126 (Pushed Authorization Requests) |
| Verification source | https://www.rfc-editor.org/rfc/rfc9396 and IANA RAR registry |

## Plan

1. Identify the deployment context (authorization server, resource server, client, gateway, mid-tier resource API).
2. Map required behaviour against RFC 9396 § 4–§ 6 (data model, request format, default and registered `type` values, authorization request and token issuance interaction).
3. Capture operational requirements: use of PAR (RFC 9126) to lock down RAR parameters, client metadata (`authorization_details_types_supported` per RFC 8414 / RFC 9396 § 4), policy evaluation, and consumable resource-level token shape (e.g., RFC 8693 token exchange of RAR-constrained tokens).
4. Validate against the live IANA RAR registry (`Authorization Details Type` registry) and AS Metadata `authorization_details_types_supported`.

## Inputs

- Authorisation detail type list the AS advertises and accepts (e.g., `"openid_credential"`, `"account_information"`, `"payment_initiation"`, plus custom types per AS policy).
- Default-affordance posture (RFC 9396 § 4.2) — when the AS does not require RAR and a resource_signal is empty.
- PAR (RFC 9126) posture: PAR-required / PAR-optional / not supported.
- Client authentication posture (TLS client auth per RFC 8705, DPoP per RFC 9449, JWT-based private_key_jwt).
- Downstream token handling (introspection per RFC 7662, RFC 8693 token-exchange, or self-contained JWT with RAR claims per RFC 9396 § 7).

## ORCHORDS Profile

This guide is used as a reference when reviewing OAuth 2.0 authorization-flow documentation or designing fine-grained authorisation posture. It does NOT introduce protocol behaviour beyond what the RFCs and IANA registries specify. When a behavioural rule that is not captured here is required by a RAR operation, escalate to a fresh review against the current RFC and the relevant IANA registry.

## Implementation Notes

- Pair RAR with PAR (RFC 9126) when high-assurance consent or signed request parameters are required; forward `authorization_details` as-is through the PAR push (RFC 9396 § 5).
- For sensitive resources, declare RAR type explicitly and reject coarse scopes only — never mix coarse scope-deny with RAR-allow in the same permission decision.
- Use RFC 8693 token exchange to mint a short-lived, RAR-narrowed token for downstream services; never assume coarse scopes stay coarse.
- When using JWT access tokens (RFC 7519 / RFC 9068), encode RAR claims inside the token with explicit audience-binding (RFC 9396 § 7.1).
- Surface RAR type list to clients via AS Metadata (RFC 8414) `authorization_details_types_supported`; reject unknown types per AS policy.
- For sender-constrained RAR tokens, prefer DPoP (RFC 9449) over mTLS where stateless binding is preferred; treat both as transport-binding per RFC 9700.

## Companion Documents

- RFC 6749 (OAuth 2.0)
- RFC 6750 (OAuth 2.0 Bearer Token Usage)
- RFC 7662 (OAuth 2.0 Token Introspection)
- RFC 7519 (JWT)
- RFC 7515 (JWS) / RFC 7517 (JWKS)
- RFC 8414 (Authorization Server Metadata)
- RFC 8693 (Token Exchange)
- RFC 9068 (JWT Profile for OAuth 2.0 Access Tokens)
- RFC 9126 (Pushed Authorization Requests)
- RFC 9449 (DPoP)
- RFC 9700 (OAuth 2.0 Security BCP)
- IANA RAR `Authorization Details Type` registry
