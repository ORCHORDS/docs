---
title: "X.509v3 Transport Layer Security (TLS) Feature Extension: Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# X.509 TLS Feature Extension

## Normative protocol requirements

OID `1.3.6.1.5.5.7.1.24` contains a nonempty sequence of TLS extension numbers assigned in the IANA TLS ExtensionType Values registry. Value 5 requires `status_request` (Must-Staple). A client understanding the certificate extension rejects a handshake lacking the required feature and still validates the stapled OCSP response; the extension does not make stale status valid.

## Validation and interoperability

Decode DER and verify OID, sequence and integer range. Test valid, missing, expired, malformed, wrong-CertID and unauthorized-signer staples across every TLS termination path. Monitor nextUpdate and refresh margin before deploying the certificate.

## Meaningful failure handling

When a recognized certificate TLS Feature is unsatisfied, fail the handshake despite successful path validation. For Must-Staple, retain feature 5, staple presence, CertID, signer, signature, and freshness evidence; missing, malformed, mismatched, or stale OCSP is not soft success.

## Canonical sources

- [RFC 7633](https://www.rfc-editor.org/rfc/rfc7633)
