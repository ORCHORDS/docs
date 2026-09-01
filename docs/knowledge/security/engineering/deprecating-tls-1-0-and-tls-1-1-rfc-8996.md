---
title: "Deprecating TLS 1.0 and TLS 1.1 (RFC 8996)"
owner: Documentation Maintainer
status: approved
visibility: public
last-reviewed: 2026-09-01
review-cycle: 90 days
next-review: 2026-11-30
---

# Deprecating TLS 1.0 and TLS 1.1

## Normative protocol requirements

RFC 8996 deprecates TLS 1.0, TLS 1.1, and DTLS 1.0; these versions must not be negotiated; DTLS 1.2 is not deprecated by RFC 8996. Failure to agree uses fatal `protocol_version`. Legacy ClientHello record-version compatibility does not permit obsolete negotiation.

## Validation and interoperability

Force each obsolete version against every edge, SNI, origin, IPv4/IPv6 path and require failure; then prove TLS 1.2/1.3 succeeds. Capture negotiated versions and resumptions. Alert on any successful version below TLS 1.2.

## Meaningful failure handling

Terminate negotiation of TLS 1.0, TLS 1.1, or DTLS 1.0 with the applicable fatal version failure rather than retrying an obsolete version. Record offered and negotiated versions, endpoint, and policy path; a later modern-version success must not hide the prohibited attempt.

## Canonical sources

- [RFC 8996](https://www.rfc-editor.org/rfc/rfc8996)
