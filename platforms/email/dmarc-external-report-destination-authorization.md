# DMARC external aggregate-report destination authorization

**Issue:** A DMARC policy that sends aggregate reports to another organizational domain can be abused to direct unsolicited report traffic unless the destination explicitly authorizes it.
**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- For every cross-domain `rua` URI, require the destination to publish the DMARC external-report authorization record defined by the protocol.
- Resolve authorization before sending reports and cache only within DNS TTLs. A missing, temporary-error, or malformed response must not be treated as permanent permission.
- Keep report receivers separate from interactive mailboxes; impose message-size, rate, decompression, XML parser, and retention limits.
- Minimize exposed data, document privacy handling, and authenticate access to stored aggregate reports.
- Maintain an owner map for each reporting destination and remove stale authorization when a vendor or domain changes.

## Verification

1. Parse the live DMARC record and enumerate each `rua` destination by organizational domain.
2. Query the corresponding authorization name and verify it authorizes the requesting policy domain.
3. Test unauthorized and NXDOMAIN destinations; assert the reporter omits them without blocking other authorized recipients.
4. Feed oversized, compressed-bomb, malformed XML, duplicate, and replayed reports into the intake pipeline.
5. Compare expected reporter/domain/day tuples to received data and alert on sudden silence or abnormal volume.

## Gotchas

The authorization check is between domains, not proof that an individual mailbox is safe or monitored. Wildcard authorization intentionally broadens trust and needs explicit risk acceptance. DMARC aggregate XML is untrusted input even when delivered to an authorized address. Multiple `rua` URIs can have different authorization outcomes.

## Sources

- [RFC 7489, section 7.1: Verifying External Destinations](https://www.rfc-editor.org/rfc/rfc7489.html#section-7.1)
- [RFC 7489, section 6.3: General Record Format](https://www.rfc-editor.org/rfc/rfc7489.html#section-6.3)
