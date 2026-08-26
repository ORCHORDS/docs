# DNS ZONEMD validation boundary

**Issue:** A ZONEMD record provides a digest over a DNS zone at rest. Without DNSSEC it is only a checksum against unintended change; origin authenticity requires validating the DNSSEC chain and the signed apex ZONEMD and SOA records before trusting the recomputed digest.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Decide from local trust anchors and the parent DS chain whether DNSSEC records and a signed ZONEMD record are expected.
- Require the ZONEMD RRset at the zone apex and validate its existence or authenticated denial under DNSSEC where signatures are expected.
- Validate the SOA and ZONEMD RRset signatures to the configured trust anchor.
- Require the ZONEMD Serial to equal the current SOA Serial exactly.
- Reject duplicate Scheme and Hash Algorithm tuples; apply an explicit allowlist and algorithm-transition policy.
- Recompute the digest from the complete canonical zone according to RFC 8976 and compare it in constant-time where the implementation provides that facility.
- Stage zone transfers or file imports and refuse publication when required verification fails.
- Preserve source, transfer identity, SOA serial, trust-anchor set, signatures, algorithms, computed digest, expected digest, verifier version, time, and decision.
- Rate-limit any query surface and never calculate a whole-zone digest dynamically for each DNS request.

## Implementation and tests

Test a signed valid zone, unsigned checksum-only zone, missing apex ZONEMD, authenticated denial, invalid SOA or ZONEMD signature, serial mismatch, one-record mutation, added or removed delegation or glue, truncation, unsupported algorithm, duplicate tuple, algorithm rollover, expired signature, and changed trust anchor. Compare multiple presentation formats that encode the same canonical zone.

Verify before loading the new zone into authoritative service, and keep the last known-good version for rollback. Recalculate during publication, not per query.

## Gotchas

ZONEMD complements rather than replaces DNSSEC: it protects the zone as a whole, including records not individually signed, while DNSSEC authenticates whether and what digest to expect. An unsigned matching digest cannot distinguish an attacker’s consistently modified zone and digest.

RFC 8976 is optional to implement and its whole-zone calculation is impractical for some large or frequently changing zones. Check server and tooling support before making it a mandatory gate.

## Official sources

- [RFC 8976: Message Digest for DNS Zones](https://www.rfc-editor.org/rfc/rfc8976.html)
- [RFC Editor: RFC 8976 status](https://www.rfc-editor.org/info/rfc8976/)
