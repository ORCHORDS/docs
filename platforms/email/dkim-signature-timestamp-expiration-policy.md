# DKIM Signature Timestamp and Expiration Policy

**Issue:** DKIM signatures remain replayable for an undefined period, or aggressive expiration makes delayed legitimate mail fail authentication; teams also treat expiration as complete replay prevention.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Set the DKIM `t=` signature timestamp from a synchronized clock and choose an `x=` expiration only from a documented delivery/retry window. RFC 6376 requires `x`, when present, to be later than `t`. Rotate selectors and keys independently; expiration limits a signature's validity window but does not revoke a key or stop copies replayed inside that window.

At verification, distinguish cryptographic failure, expired signature, future timestamp beyond clock-skew policy, missing optional timestamps, and policy rejection. Preserve other authentication signals and DMARC alignment; do not turn an expired DKIM result into an automatic content verdict. Monitor delivery latency before tightening the window.

## Verification

Test absent `t`/`x`, valid window, boundary expiry, `x <= t`, clock skew, delayed queues, forwarding, duplicate messages inside/outside the window, key rotation, and canonicalization changes. Confirm signer and verifier clocks are monitored and receivers still process authentication according to published semantics.

## Gotchas

The `x=` tag is optional in DKIM and receiver handling can vary. Expiration is not message uniqueness, nonce validation, or revocation. Short windows harm queued or intermittently connected delivery; long windows provide less replay reduction. Do not rely on an unsigned Date header as the signature clock.

## Sources

- [IETF RFC 6376 — DomainKeys Identified Mail Signatures](https://datatracker.ietf.org/doc/html/rfc6376)
- [IETF RFC 7489 — DMARC](https://datatracker.ietf.org/doc/html/rfc7489)
