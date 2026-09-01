---
title: "FAPI 2.0 Security Profile"
owner: Documentation Maintainer
status: approved
visibility: public
last-reviewed: 2026-09-01
review-cycle: 90 days
next-review: 2026-11-30
---

# FAPI 2.0 Security Profile

## Normative contract

FAPI 2.0 uses authorization code, PAR, S256 PKCE and sender-constrained tokens. Bind each short-lived request_uri to its authenticated client. Select DPoP or mTLS end to end. DPoP validation covers signature/key, htm, htu, iat, unique jti, ath and nonce when used; mTLS validation compares the request certificate with token confirmation.

Algorithm policy is an allow-list derived from metadata and registration. Reject `none`, unexpected symmetric algorithms, unknown keys, algorithm/key-type mismatch, stale objects, duplicated security-sensitive claims, and conflicting parameters. An invalid redirect URI is handled locally and is never used to deliver an OAuth error. Back-channel errors use the defined OAuth error form without revealing whether guessed credentials or accounts exist. No failed profiled exchange may retry through a bearer, unsigned, or otherwise weaker compatibility path.

## Engineering and governance workflow

Publish one deployment contract covering issuer, endpoints, flows, response modes, authentication method, signing algorithms, redirect URIs, token audiences, proof lifetimes, clock skew, and rotation. Separate signing, assertion and transport keys where practical. Inventory every proxy and resource server; certificate or proof identity forwarded by a gateway must travel over an authenticated trusted hop and headers from untrusted peers must be removed. Assign owners for client registration, key rollover, endpoint changes and time-bounded exceptions.

Process requests in explicit stages: authenticate the registered client; validate the protected request and transaction bindings; perform user authorization; bind and issue the code; validate token exchange; then enforce token and business authorization independently at the API. Log correlation identifiers and rejection classes, never tokens, codes, assertions, private keys or personal data.

## Failure modes and verification

Test response injection, mix-up, redirect manipulation, code interception and replay, assertion replay, wrong issuer or audience, altered signed content, stale timestamps, key substitution, and token use at the wrong API. Where sender constraint applies, steal a token in a controlled test and prove that a different certificate or proof key cannot use it. Exercise direct origins as well as public gateways. Expiry and replay caches must work across clustered nodes.

Run the matching OpenID Foundation conformance plan for the exact options deployed. Preserve the suite version and configuration, machine-readable results, metadata and registration snapshots, redacted protocol traces, key identifiers and rollover results, proxy trust configuration, and API-side denials. Review evidence after changes to clients, algorithms, endpoints, gateways or TLS termination; a happy-path token issuance alone does not prove profile compliance.

## Authoritative sources

- [Canonical specification](https://openid.net/specs/fapi-security-profile-2_0-final.html)
