# Operate TLS ECH Configuration Rotation and Fallback

**Issue:** Encrypted Client Hello protects SNI and other ClientHello fields only when clients obtain a valid ECH configuration, the server accepts it, and fallback/retry behavior is correct.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Publish ECH configuration through the RFC-defined HTTPS/SVCB mechanism and bind it to the intended client-facing server.
- Rotate ECH keys with overlap for DNS cache and client retry lifetimes.
- Keep externally visible TLS behavior aligned across the anonymity set.
- Distinguish ECH acceptance, rejection, GREASE, retry, and `ech_required` failures in telemetry.
- Never report a rejection connection authenticated only for the public name as application success.

## Verification
- Test fresh, stale, unknown, and overlapping config IDs across distributed edges.
- Exercise HelloRetryRequest, retry configs, downgrade/fallback policy, and DNS propagation.
- Compare observable outer behavior across backend members.

## Gotchas
ECH does not hide destination IP and does not authenticate the private origin by itself. Misconfigured fallback can silently restore plaintext ClientHello exposure.

## Official sources
- [RFC 9849](https://www.rfc-editor.org/rfc/rfc9849.html)
- [RFC 9848: ECH configuration in SVCB/HTTPS](https://www.rfc-editor.org/rfc/rfc9848.html)
