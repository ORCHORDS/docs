---
title: "DNS Security (DNSSEC) Hashed Authenticated Denial of Existence: Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# NSEC3 Authenticated Denial

## Normative protocol requirements

NXDOMAIN requires closest-encloser, next-closer coverage, and wildcard nonexistence proofs; NODATA proves name existence and type absence. Hashes use fully qualified canonical owner names in lowercase DNS wire format; NSEC3 owner hashes use base32hex (the Extended Hex Alphabet) without padding, and hash ordering is circular unsigned-octet ordering. Opt-Out can establish insecure unsigned delegations, never secure data. RFC 9276 recommends iteration count zero and empty salt for new zones.

## Validation and interoperability

Verify NXDOMAIN, exact-name NODATA, empty nonterminal, wildcard, opt-out, wrap-around, malformed base32hex, mixed parameters, and missing proof components. Enforce iteration work limits. Incomplete proofs are bogus/SERVFAIL.

## Meaningful failure handling

Classify the answer as bogus when NSEC3 records do not prove the applicable closest-encloser, next-closer, wildcard, or requested-type absence. Return SERVFAIL normally and retain owner hashes, parameters, opt-out decision, and the missing or inconsistent proof component.

## Canonical sources

- [RFC 5155 and RFC 9276](https://www.rfc-editor.org/rfc/rfc5155)
