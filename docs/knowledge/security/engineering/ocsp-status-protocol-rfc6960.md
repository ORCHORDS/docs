---
title: "X.509 Internet Public Key Infrastructure Online Certificate Status Protocol - OCSP: Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# OCSP Response Validation

## Normative protocol requirements

Match CertID issuer-name hash, issuer-key hash, serial and hash algorithm. `good` means no revocation is recorded, not proof of issuance; never map `unknown` to good. Verify exact DER tbsResponseData. The signer is the CA, explicitly trusted responder, or directly delegated certificate with `id-kp-OCSPSigning`. Check producedAt, thisUpdate and nextUpdate policy.

## Validation and interoperability

Test wrong CertID, unauthorized signer, missing EKU, expired responder, altered TBS, critical extension, stale/future times, revoked/unknown, malformed DER and unsuccessful response status. Network failure is not cryptographic good; any soft fail must be explicit.

## Meaningful failure handling

Treat malformed, unsigned, unauthorized, CertID-mismatched, stale, or future-dated responses as unusable, distinct from authenticated `revoked` or `unknown`. Record responder identity, times, CertID, signature result, and transport outcome; network failure is never `good` evidence.

## Canonical sources

- [RFC 6960](https://www.rfc-editor.org/rfc/rfc6960)
