---
title: "Online Certificate Status Protocol (OCSP) Nonce Extension: Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# OCSP Nonce Semantics

## Normative protocol requirements

RFC 9654 obsoletes RFC 8954 and controls new implementations. The nonce is inside the OCSP Extension wrapper and contains an OCTET STRING; avoid adding or removing an ASN.1 layer. RFC 9654 permits nonce values from 1 through 128 octets. A requester that includes a nonce must reject a successful response without the nonce or with a nonmatching value. A responder that accepts the nonce extension must include the identical nonce in its response; a responder that does not accept it must reject the request. Nonce use does not excuse signature, CertID or time validation.

## Validation and interoperability

Encode boundary lengths 1 and 128 and reject 0 and 129. Test exact echo, one-bit mismatch, unsolicited/duplicate nonce, malformed inner value, cache behavior, and responder rejection. Log presence, length and a keyed diagnostic digest rather than raw nonce.

## Meaningful failure handling

A requester that sent a nonce must reject a successful response that omits it or differs; a responder accepting the extension must echo it exactly. Reject malformed or out-of-range values and record request/response presence, lengths, and keyed digests without nonce bytes.

## Canonical sources

- [RFC 9654 (obsoleting RFC 8954)](https://www.rfc-editor.org/rfc/rfc9654)
