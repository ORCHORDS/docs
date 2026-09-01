---
title: "JWT Bearer Assertions for OAuth (RFC 7523)"
owner: Documentation Maintainer
status: approved
visibility: public
last-reviewed: 2026-09-01
review-cycle: 90 days
next-review: 2026-11-30
---

# JWT Bearer Assertions for OAuth (RFC 7523)

## Wire contract and normative rules

RFC 7523 defines a deliberately narrow extension point: JWT bearer assertions require iss, sub, aud and exp; client-authentication sub identifies the client. Implementers must pin issuer mappings, exact audience, algorithms and keys; check times, signature and jti replay, returning invalid_grant or invalid_client by role. Transport security is necessary but does not replace message-level issuer, audience, key, lifetime, purpose and replay validation. A syntactically valid object is not authorized merely because a parser accepts it.

Build an allow-list for algorithms, key types, issuers, audiences and endpoint identifiers from registration or local trust configuration. Do not let attacker-controlled issuer, key ID, key URL, assertion type, token hint or content type select an unrestricted key or network destination. Apply explicit size, nesting, clock-skew and lifetime limits. Separate client authentication from grant authorization and business authorization; success at one stage must not bypass the next.

## Processing and failure behavior

Parse with duplicate detection, validate encoding and media type, authenticate the message, establish the expected issuer and recipient, check time and transaction bindings, enforce one-time use, and only then act on scopes or identity. Reject malformed input, `none`, algorithm/key mismatch, unknown keys, wrong issuer or audience, expiry, premature use, replay, cross-client substitution and ambiguous duplicates. Never retry failed protected input as an unsigned or bearer alternative.

Return the specification's OAuth error and HTTP behavior without echoing credentials or distinguishing secrets that the protocol intentionally makes indistinguishable. Authorization redirects are permitted only after independently trusting the redirect URI. Logs contain correlation IDs and rejection classes, not assertions, tokens, codes, personal attributes, private keys or decrypted confidential payloads. Clustered nodes must share or consistently enforce replay and revocation state.

## Deployment workflow and evidence

Document endpoint owner, trust anchors, registration values, algorithm policy, maximum lifetime, skew, replay retention, key rollover and emergency revocation. Stage key rotation with overlapping verification only for explicitly trusted old and new keys, then prove retirement. Review proxies, caches and libraries for content-type rewriting, hidden retries and accidental secret logging.

Test a valid exchange plus bad encoding, duplicate fields, altered signature, wrong key, issuer, audience and subject, stale/future times, parallel replay, key rotation, wrong client and wrong endpoint. Where the feature changes API authorization, prove denial at the consuming API rather than stopping at the token endpoint. Preserve dated redacted wire traces, object hashes, decoded nonsecret claims, validation-stage results, key fingerprints, replay/cache observations and software/configuration versions.

## Authoritative source

- [RFC 7523](https://www.rfc-editor.org/rfc/rfc7523.html)
