---
title: "Resource Records for the DNS Security Extensions: Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# DNSSEC Resource Records and Canonical Form

## Normative protocol requirements

DNSKEY protocol is 3; DS hashes canonical owner name plus DNSKEY RDATA. RRSIG verification uses lowercase uncompressed names, original TTL and canonical RDATA ordering. Signature times are 32-bit serial values. NSEC bitmap windows increase strictly, lengths are 1–32, and trailing zero octets are forbidden.

## Validation and interoperability

Independently recompute key tags and DS. Round-trip record wire forms; test case folding, escaped labels, wildcard labels, ordering, time wrap, malformed bitmaps, unknown algorithms, and cached TTL changes. Cross-test independent signers and validators.

## Meaningful failure handling

Reject malformed DNSKEY, DS, RRSIG, or NSEC RDATA and signatures failing canonical RRset, label, time, signer, or algorithm checks. Preserve the wire RRset, canonicalization inputs, key tag, and terminal verification reason as reproducible evidence.

## Canonical sources

- [RFC 4034](https://www.rfc-editor.org/rfc/rfc4034)
