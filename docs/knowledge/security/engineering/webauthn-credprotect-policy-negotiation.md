# WebAuthn credProtect policy negotiation

**Issue:** The credential-protection extension requests authenticator policy but support and enforcement vary.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Request explicit policy, inspect extension results, align userVerification and fallback with risk.

## Tests

Unsupported authenticator, silent downgrade, discoverable/non-discoverable credentials, UV failure.

## Gotchas

A requested policy is not proof unless returned and enforced; avoid locking out legitimate authenticators.

## Official sources

- https://w3c.github.io/webauthn/#sctn-credProtect-extension
