# Govern HTTP Client Hints Negotiation and Variance

**Issue:** Client Hints are request headers selected through server opt-in. Using them without explicit variance and privacy controls can fragment caches and create fingerprinting surface.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Request only hints necessary for a defined response decision.
- Send the relevant Vary behavior and bound the cache-key dimensions.
- Treat hints as advisory, missing, rounded, or inaccurate; preserve a functional default.
- Scope and expire opt-in according to browser and response behavior.
- Perform privacy review before combining high-entropy hints.

## Verification
- Test first navigation before opt-in, later navigation, cross-origin requests, missing hints, and cache reuse.
- Compare cache cardinality before and after each hint.
- Spoof contradictory hints and confirm no authorization or safety decision depends on them.

## Gotchas
Client Hints are not durable device identity and not all user agents support the same hints. Negotiation can require an extra request before adaptation.

## Official sources
- [RFC 8942](https://www.rfc-editor.org/rfc/rfc8942.html)
- [W3C User-Agent Client Hints](https://www.w3.org/TR/ua-client-hints/)
