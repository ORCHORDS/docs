---
title: "OpenID Connect Discovery 1.0"
owner: Documentation Maintainer
status: approved
visibility: public
last-reviewed: 2026-09-01
review-cycle: 90 days
next-review: 2026-11-30
---

# OpenID Connect Discovery 1.0

## Normative protocol behavior

For issuer discovery, fetch /.well-known/openid-configuration at the issuer path transformation defined by the specification. The returned issuer must exactly equal the issuer used to obtain the configuration. Required metadata includes issuer, authorization_endpoint, jwks_uri, response_types_supported, subject_types_supported and id_token_signing_alg_values_supported. HTTPS and certificate validation apply. Never follow metadata to trust a different issuer implicitly or select keys solely by kid.

Pin issuers, clients, endpoints, algorithms and keys through authenticated registration or local configuration. Use exact URI comparison where the specification requires it, apply bounded clock skew and object lifetime, reject duplicates and unsupported critical values, and prevent an attacker-controlled identifier from triggering unrestricted network fetches. TLS endpoint authentication remains mandatory; it does not excuse message validation.

## Implementation and governance

Model the complete state machine, including pending, successful, denied, expired, logged-out, registered, updated and delivery-failed states relevant to this specification. Persist transaction binding and one-time identifiers atomically across nodes. Define owners for metadata, client registration, schema/event extensions, key rotation, redirect and callback allow-lists, privacy review, and emergency suspension. Minimize attributes and event data to the recipient's need.

Do not log credentials, ID Tokens, access tokens, authentication request IDs, passwords, full user records or sensitive event payloads. Proxies must not rewrite issuer, host, callback identity or authenticated client context unless the application consumes a trusted, integrity-protected representation. Compatibility behavior must not turn a failed protected request into an unvalidated legacy flow.

## Failure modes and verification evidence

Reject wrong issuer, audience, client, redirect/callback, signature, algorithm or key; stale and future objects; replay; malformed JSON; duplicate security fields; state mismatch; and unauthorized data or lifecycle transitions. Use the protocol-defined OAuth/OIDC/SCIM error and status behavior, but avoid responses that reveal whether an account, grant, event subject or secret exists. A redirect is used only after its registration is independently established.

Test the valid lifecycle plus cancellation, expiry, parallel replay, key rollover, another client's identifiers, altered callback or redirect, and clustered-state races. Add topic-specific negative cases from the normative paragraph above. Retain registration and metadata snapshots, redacted request/response traces, hashes and key identifiers, state-transition audit events, negative response codes, and consumer-side denial evidence. Re-run after changes to endpoints, schema/event types, delivery mode, redirect lists, keys, proxies or session topology.

## Authoritative source

- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0-final.html)
