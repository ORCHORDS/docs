# Oblivious HTTP Relay and Gateway Separation

**Issue:** Oblivious HTTP privacy depends on preventing one party from simultaneously learning client identity and plaintext request content. Colluding or co-located relay and gateway roles collapse that property.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Operate relay and gateway under independent trust and logging boundaries when unlinkability is required.
- Encrypt encapsulated requests to the gateway configuration and validate configuration freshness.
- Minimize relay metadata and gateway application identifiers; define abuse controls that do not recreate a stable user identifier.
- Threat-model traffic analysis, size, timing, retries, and collusion.

## Verification

- Confirm the relay cannot decrypt requests and the gateway does not receive the client network address.
- Rotate gateway keys and test stale-configuration failure/recovery.
- Review logs to verify neither side reconstructs the forbidden linkage.

## Gotchas

- OHTTP hides request content from the relay, not traffic timing and size.
- A direct client fallback can silently bypass the privacy design.

## Official sources

- https://www.rfc-editor.org/rfc/rfc9458.html
