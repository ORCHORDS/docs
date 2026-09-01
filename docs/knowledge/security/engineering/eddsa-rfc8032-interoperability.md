---
title: "Edwards-Curve Digital Signature Algorithm (EdDSA): Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# EdDSA Encoding and Interoperability

## Normative protocol requirements

Ed25519 public keys are 32-byte compressed points; signatures are exactly 64 bytes: encoded R then little-endian scalar S. Ed448 uses 57-byte keys and 114-byte signatures. Reject noncanonical points and `S >= L`. Pure, context, and prehash variants are distinct; context length is at most 255 octets, and passing a digest to pure Ed25519 is not Ed25519ph.

## Validation and interoperability

Run all applicable RFC vectors. Mutate R, S, sign bit, context and message. Reject wrong lengths, noncanonical y, invalid points, and S equal to or above L. Cross-verify libraries and label variant/context explicitly at API boundaries.

## Meaningful failure handling

Reject wrong lengths, non-canonical encodings, invalid points, or failed equations for the selected Ed25519 or Ed448 variant and context. Expose one verification-failure result while retaining variant, context length, public-key fingerprint, and vector identifier internally.

## Canonical sources

- [RFC 8032](https://www.rfc-editor.org/rfc/rfc8032)
