# JWT RFC 8725 validation profile

**Issue:** A generic JWT validator accepts attacker-selected algorithms, wrong token types, or claims from another security context.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Follow RFC 8725 / BCP 225. Allowlist algorithms per token profile; never derive acceptance from `alg` alone. Validate signature/key, issuer, audience, time claims, token type, and profile-required claims. Use distinct keys, audiences, explicit typing, and validation rules for different JWT kinds. Reject duplicate/ambiguous JSON and unsafe compression/encryption composition.

## Verification

Test `none`, algorithm substitution, weak keys, wrong issuer/audience/type, expired/not-yet-valid, duplicate claims, cross-token substitution, and key rotation.

## Gotchas

Decoding is not validation. A valid signature does not establish correct audience or purpose. Clock leeway must be bounded and monitored.

## Sources

- [RFC 8725 / BCP 225](https://www.rfc-editor.org/info/rfc8725/)
