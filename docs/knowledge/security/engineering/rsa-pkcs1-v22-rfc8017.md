---
title: "PKCS #1: RSA Cryptography Specifications Version 2.2: Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# RSA PKCS #1 v2.2

## Normative protocol requirements

RSA octet strings are fixed length `k` and unsigned big-endian; reject representatives outside `[0,n-1]`. OAEP bounds plaintext to `k-2*hLen-2`, binds the label, and requires matching hash/MGF parameters. Merge all decoding failures. PSS enforces hash/MGF/salt profile, unused high bits and trailer `0xbc`; maximum salt is `emLen-hLen-2`.

## Validation and interoperability

Mutate OAEP delimiters, label hash, masks and leading byte; mutate PSS high bits, salt and trailer. Exercise exact bounds and non-byte-aligned moduli. PKCS1-v1_5 verification must parse exact DER DigestInfo with no trailing data. Apply blinding and CRT fault protections.

## Meaningful failure handling

Return one indistinguishable decryption or verification failure for OAEP, PSS, or PKCS1-v1_5 encoding errors, retaining only non-secret diagnostics. Never reveal the failed padding field, release partial plaintext, or accept trailing or non-canonical `DigestInfo` data.

## Canonical sources

- [RFC 8017](https://www.rfc-editor.org/rfc/rfc8017)
