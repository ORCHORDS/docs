# WebAuthn Signal API credential reconciliation

**Issue:** The WebAuthn Level 3 editor's draft defines signal methods that let a relying party help an authenticator reconcile credentials, including unknown credentials and accepted credential lists. Treat these APIs as draft, capability-dependent enhancements, not authentication decisions.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Feature-detect each signal method and call it only after the server has established the relevant account/credential fact.
- Validate RP context, avoid exposing cross-account credential inventories, and rate-limit reconciliation signals.
- Keep server revocation authoritative; record coarse outcomes without credential IDs in analytics.

## Verification

1. Test unsupported browsers, stale lists, multi-device credentials, account switching, and malicious credential IDs.
2. Prove login denial/revocation works when every signal call fails.
3. Confirm no accepted-credential list crosses tenant or account boundaries.

## Gotchas

A signal is advisory and may be ignored. The cited WebAuthn Level 3 document is an Editor's Draft and can change; do not gate account safety on browser support.

## Official sources

- https://w3c.github.io/webauthn/
