# WebAuthn cross-origin iframe top-origin binding

**Issue:** Cross-origin WebAuthn ceremonies expose topOrigin/crossOrigin context that the RP must validate rather than trusting the embedded caller alone.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Allowlist embedding/top origins, enforce Permissions Policy, validate RP ID and challenge server-side, deny unexpected cross-origin context.

## Tests

Nested iframe, changed top origin, missing policy, clickjacking, related origins, same-origin regression.

## Gotchas

CORS does not grant WebAuthn capability and iframe permission does not replace server checks.

## Official sources

- https://w3c.github.io/webauthn/#sctn-validating-origin
