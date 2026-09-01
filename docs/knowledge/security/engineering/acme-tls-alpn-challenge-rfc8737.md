---
title: "Automated Certificate Management Environment (ACME) TLS Application-Layer Protocol Negotiation (ALPN) Challenge Extension: Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# ACME TLS-ALPN-01 Challenge

## Normative protocol requirements

Hash the RFC 8555 key authorization with SHA-256. The temporary certificate has exactly one SAN `dNSName` and a critical `acmeIdentifier` extension, OID `1.3.6.1.5.5.7.1.31`, whose OCTET STRING is the 32-byte digest. Validation uses TCP 443 and ALPN `acme-tls/1`; the server must select it.

## Validation and interoperability

Inspect DER for OID, critical bit, OCTET STRING, digest, and single SAN. Test wrong SNI/ALPN, extra SAN, stale token, ordinary certificate, and multi-tenant routing. Remove the temporary key after authorization.

## Meaningful failure handling

Fail authorization unless ALPN is exactly `acme-tls/1` and the temporary certificate has a critical `id-pe-acmeIdentifier` containing the matching digest. Record SNI, negotiated ALPN, certificate fingerprint, and ACME problem type; do not fall through to another virtual host.

## Canonical sources

- [RFC 8737](https://www.rfc-editor.org/rfc/rfc8737)
