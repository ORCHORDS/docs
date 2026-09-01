---
title: "Protocol Modifications for the DNS Security Extensions: Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# DNSSEC Protocol Validation

## Normative protocol requirements

Validate from trust anchor through DNSKEY and DS to canonical signed RRsets, including RRSIG algorithm, key tag, signer, labels, original TTL, inception and expiration. DO requests records, CD disables checking, and AD asserts authenticated data; never copy untrusted upstream AD. Wildcards require authenticated denial.

## Validation and interoperability

Test positive, CNAME, referral, insecure delegation, NXDOMAIN/NODATA, wildcard, time boundaries, TTL changes, unsupported algorithm, missing key, and DO/CD/AD combinations. Bogus normally yields SERVFAIL with AD clear. Cache persistent bogus failures only for a bounded interval per RFC 9520.

## Meaningful failure handling

On RRset, delegation, or denial-proof failure, clear AD and return SERVFAIL normally; never relabel bogus data as insecure. Record the trust anchor, signer, key tag, algorithm, validation time, and failed proof step, while bounding cached failure duration.

## Canonical sources

- [RFC 4035](https://www.rfc-editor.org/rfc/rfc4035)
