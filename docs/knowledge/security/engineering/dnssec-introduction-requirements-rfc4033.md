---
title: "DNS Security Introduction and Requirements: Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# DNSSEC Security Model and Resolver States

## Normative protocol requirements

Keep validation states distinct: secure chains to a trust anchor; insecure is authenticated absence of a secure delegation; bogus is expected validation that failed; indeterminate lacks enough trust information. Never convert bogus to insecure. DNSSEC authenticates RRsets and denial proofs; it provides no confidentiality. RFC 4035 permits a stub to rely on AD only over a secure channel to a trusted recursive resolver. RFC 4033 distinguishes a validating stub, which performs its own validation, from a non-validating security-aware stub using CD/AD semantics; a validating stub can set CD and validate the returned DNSSEC data itself.

## Validation and interoperability

Exercise valid signed, authenticated unsigned delegation, altered RDATA, expired RRSIG, DS/DNSKEY mismatch, NXDOMAIN/NODATA, unknown algorithm, and no-anchor cases. Check CD returns unchecked data with AD clear and normal bogus answers produce SERVFAIL.

## Meaningful failure handling

A failed expected validation is bogus, not insecure; ordinary validating resolution returns SERVFAIL rather than unverified data. If CD requests unchecked data, clear AD and retain the failed chain, RRset, algorithm, and validation-time evidence.

## Canonical sources

- [RFC 4033](https://www.rfc-editor.org/rfc/rfc4033)
