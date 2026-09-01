---
title: "Transport Layer Security (TLS) Application-Layer Protocol Negotiation Extension: Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# TLS Application-Layer Protocol Negotiation

## Normative protocol requirements

The client offers an ordered list of opaque nonempty protocol names, each 1–255 octets. Comparison is exact bytes. The server selects exactly one offered value; no match causes fatal `no_application_protocol`. TLS 1.2 carries selection in ServerHello and TLS 1.3 in EncryptedExtensions. Resumption/0-RTT must retain compatible interpretation.

## Validation and interoperability

Test order reversal, one/none/unknown protocols, empty/duplicate/maximal names, malformed lengths, unoffered selection, SNI policy, resumption and early data. Dispatch only after authenticated negotiation; missing ALPN is fallback only where the application specification defines it.

## Meaningful failure handling

Abort with `no_application_protocol` when no offered protocol is supported; never select an unoffered value. Record the offered list, selection, endpoint, and alert, and permit absent-ALPN fallback only where the application specification defines it.

## Canonical sources

- [RFC 7301](https://www.rfc-editor.org/rfc/rfc7301)
