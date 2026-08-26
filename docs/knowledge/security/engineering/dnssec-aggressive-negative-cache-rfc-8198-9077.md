# Bound DNSSEC Aggressive Negative Caching

**Issue:** A validating resolver can synthesize NXDOMAIN, NODATA, and wildcard answers from cached NSEC/NSEC3 proofs, amplifying both efficiency and the impact of stale or poisoned denial records.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Synthesize only from DNSSEC-validated proofs that cover the queried name and required wildcard conditions.
- Apply RFC 9077's updated NSEC/NSEC3 TTL rules and cap effective negative lifetime.
- Respect checking-disabled behavior and fall back to authoritative queries when proof is insufficient.
- Separate aggressive synthesis metrics from ordinary exact negative-cache hits.
- Flush affected proof ranges during signed-zone incident response.

## Verification
- Test NSEC, NSEC3, opt-out, wildcard, empty-nonterminal, CD-bit, expiry, and signature-expiration cases.
- Add a previously nonexistent name during a cached denial window and measure activation delay.
- Compare synthesized answers with authoritative validation traces.

## Gotchas
One accepted stale proof can suppress many names. This is DNSSEC validation behavior, not permission to infer nonexistence from unsigned negative answers.

## Official sources
- [RFC 8198](https://www.rfc-editor.org/rfc/rfc8198.html)
- [RFC 9077](https://www.rfc-editor.org/rfc/rfc9077.html)
