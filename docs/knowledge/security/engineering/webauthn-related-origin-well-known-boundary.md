# WebAuthn related-origin well-known boundary

**Issue:** WebAuthn Level 3 related-origin requests let multiple registrable domains use a common RP ID through an HTTPS `/.well-known/webauthn` allowlist. Treat this Editor's Draft feature as optional and capability-dependent.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Keep a small reviewed exact-origin list; serve JSON over HTTPS without credentials/referrer; validate server-side origins independently; stage additions/removals and monitor capability support.

## Verification

Test wrong media type/status, redirects to HTTP, malformed/oversized lists, lookalike domains, removed origins, unsupported clients, and common-RP-ID ceremonies.

## Gotchas

The document delegates use of one RP ID; it does not merge cookies or accounts. Cached allowlists and existing credentials complicate emergency removal.

## Official sources

- https://w3c.github.io/webauthn/#sctn-related-origins
