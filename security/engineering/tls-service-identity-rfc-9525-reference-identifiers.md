# Verify TLS Service Identity Against Reference Identifiers

**Issue:** Validating a certificate chain without matching the application's reference identifier authenticates a key, not the intended service.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Construct the reference identifier from trusted user input or configuration before connection establishment.
- Match DNS-ID, IP-ID, SRV-ID, or URI-ID according to the application protocol profile and RFC 9525.
- Do not fall back from a failed direct identifier to a discovered target name.
- Prohibit common-name matching and wildcard interpretations outside the RFC rules.
- Log identifier type and failure category without exposing certificate secrets.

## Verification
- Test DNS names, IP addresses, IDNA A-labels, service-restricted identifiers, wildcards, redirects, and discovery targets.
- Present a valid chain for the wrong service and assert failure.
- Verify every TLS/DTLS/QUIC client stack uses the same policy.

## Gotchas
Certificate issuance success and trust-chain validation do not establish service identity. Indirect names used for routing are not automatically valid replacement identities.

## Official sources
- [RFC 9525](https://www.rfc-editor.org/rfc/rfc9525.html)
