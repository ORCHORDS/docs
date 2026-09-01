---
title: "DNS over Dedicated QUIC Connections: Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# DNS over QUIC

## Normative protocol requirements

DoQ uses UDP 853 and ALPN `doq`. Each query and response occupies one client-initiated bidirectional QUIC stream with DNS-over-TCP’s two-byte length prefix. Exactly one query/response pair is permitted per stream; each sender closes its side. DNS does not use unidirectional or server-initiated streams. Responses may complete out of order. QUIC 0-RTT is replayable.

## Validation and interoperability

Run concurrent streams with delayed responses and verify out-of-order completion. Test split/mismatched lengths, extra messages, forbidden stream types, resets, migration, ALPN/certificate mismatch, and replay-sensitive operations in 0-RTT. Never silently fall back to cleartext in strict mode.

## Meaningful failure handling

On QUIC handshake, authentication, stream, or DNS framing failure, retain the applicable QUIC or DoQ error and do not parse partial bytes as a DNS response. Distinguish transport failure from DNS response codes and never silently fall back to cleartext in strict mode.

## Canonical sources

- [RFC 9250](https://www.rfc-editor.org/rfc/rfc9250)
