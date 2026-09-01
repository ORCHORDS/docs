---
title: "Elliptic Curves for Security: Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# X25519 and X448 Interoperability

## Normative protocol requirements

X25519 inputs and outputs are 32-byte little-endian strings; X448 uses 56. X25519 clears scalar bits 0–2 and 255, sets bit 254, and masks the input u-coordinate high bit. X448 clears scalar bits 0–1 and sets bit 447. When the consuming protocol or security profile requires contributory behavior, reject an all-zero shared output using a constant-time comparison. The primitive gives no peer authentication.

## Validation and interoperability

Run RFC one-, 1,000-iteration and Alice/Bob vectors. Cross-test raw keys between libraries; test high-bit compatibility, wrong lengths, ASN.1 wrapping, byte reversal, and small-order inputs. Bind output to roles and transcript through a KDF.

## Meaningful failure handling

Reject wrong-length inputs and treat an all-zero shared secret as key-agreement failure when required by the consuming protocol. Record the function and lengths, never private scalars or shared secrets, and do not use an unauthenticated result directly as an application key.

## Canonical sources

- [RFC 7748](https://www.rfc-editor.org/rfc/rfc7748)
