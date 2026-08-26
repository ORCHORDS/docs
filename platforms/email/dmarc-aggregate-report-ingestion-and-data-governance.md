# DMARC aggregate report ingestion and data governance

**Issue:** Aggregate DMARC reports are operational evidence, not a direct verdict on inbox placement. Their XML payloads can be malformed, duplicated, delayed, or contain data that must be handled under an organization's privacy and retention controls.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## What reports mean

DMARC receivers can send aggregate reports to the reporting URI in the domain's DMARC record. A report summarizes message counts and authentication/alignment results for a reporting interval. It does not prove that every message was delivered, and it should be reconciled with sending inventory and provider telemetry.

## Safe ingestion design

- Accept reports only through a dedicated mailbox or endpoint; keep report parsing isolated from user-facing mail processing.
- Verify the recipient URI authorization flow where it applies, especially when reports are requested for an external destination.
- Treat XML, compressed attachments, and metadata as untrusted input: impose size, type, decompression, parser, and rate limits.
- Deduplicate by reporting organization, report identifier, policy domain, and date range before aggregation.
- Preserve raw reports for a defined, access-controlled retention period; store derived aggregates separately so that reprocessing remains possible.
- Normalize identifiers and separate per-source IP or domain data from product analytics. Apply access control, retention, and deletion rules appropriate to the organization.
- Alert on material changes in volume, aligned-pass rates, unknown legitimate sources, and persistent policy failures; investigate before tightening a DMARC policy.

## Validation checklist

1. Confirm the DMARC record and `rua` destinations are intentional.
2. Test a representative report through the entire ingestion pipeline.
3. Reconcile expected sending services and subdomains against report aggregates.
4. Review parser failures and dropped/decompressed-size events.
5. Document who can access raw reports and when they are deleted.

## Sources

- [RFC 7489 — DMARC](https://datatracker.ietf.org/doc/html/rfc7489)
- [IETF DMARC working group](https://datatracker.ietf.org/wg/dmarc/about/)

## Tags

`email` `dmarc` `reporting` `deliverability` `privacy`
