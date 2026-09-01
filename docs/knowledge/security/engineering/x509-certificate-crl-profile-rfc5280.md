---
title: "Internet X.509 Public Key Infrastructure Certificate and Certificate Revocation List (CRL) Profile: Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# X.509 Certificate and CRL Profile

## Normative protocol requirements

Path validation checks signatures, time, chaining, basicConstraints, path length, keyUsage, EKU, policies, name constraints and every recognized critical extension. Unknown critical extensions invalidate a path. CA certificates assert cA TRUE and, when KU exists, keyCertSign. Trust anchors are inputs, not ordinary path certificates. CRLs require issuer/scope, signature, time and delta/base matching.

## Validation and interoperability

Test alternate paths, expiry, CA=false issuer, path exhaustion, KU/EKU, DNS/IP constraints, unknown critical extensions, policies, malformed DER, revoked serial, stale/wrong-scope and indirect CRLs, and mismatched delta base. Record chosen path, anchor, validation time and terminal reason.

## Meaningful failure handling

Fail path validation for an unhandled critical extension, constraint violation, invalid signature, time failure, or unresolved revocation requirement. Record candidate path, anchor, validation time, policy inputs, CRL identifiers, and terminal reason without a weaker reinterpretation.

## Canonical sources

- [RFC 5280](https://www.rfc-editor.org/rfc/rfc5280)
