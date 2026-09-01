---
title: "Specification for DNS over Transport Layer Security (TLS): Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# DNS over TLS

## Normative protocol requirements

DoT uses TCP 853 and every message has a two-octet length prefix; TCP reads are not message boundaries. Clients should pipeline and servers must support it. Responses can arrive out of order and require DNS-ID/question correlation. RFC 8310 strict mode authenticates a configured resolver name or pin and must not fall back to unauthenticated DNS.

## Validation and interoperability

Test fragmented and coalesced frames, reversed pipelined responses, duplicate IDs with distinct questions, idle reuse, and oversized lengths. Verify SNI, chain and reference identity. Ensure strict TLS failure is terminal, while opportunistic mode is labeled distinctly.

## Meaningful failure handling

In strict mode, certificate, name, handshake, or framing failure is terminal and must not trigger cleartext fallback. In opportunistic mode, record the transport actually used and the fallback reason so a transport failure cannot be presented as an authenticated DNS answer.

## Canonical sources

- [RFC 7858 and RFC 8310](https://www.rfc-editor.org/rfc/rfc7858)
