---
title: "HMAC-based Extract-and-Expand Key Derivation Function (HKDF): Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# HKDF Extract-and-Expand

## Normative protocol requirements

Extract computes `PRK = HMAC(salt, IKM)`; absent salt is HashLen zero octets. Expand uses `T(i)=HMAC(PRK,T(i-1)||info||i)` with a one-octet counter. Therefore `0 <= L <= 255*HashLen`; reject larger requests. Extraction is needed for nonuniform inputs. `info` must bind protocol, version, role and purpose.

## Validation and interoperability

Run every RFC SHA-256/SHA-1 vector, including empty salt/info. Test L at 0, 1, HashLen, 255*HashLen and one beyond. Preserve binary fields exactly, calculate each T block independently, prohibit PRK as an application key, and reject cross-purpose info reuse.

## Meaningful failure handling

Fail when output exceeds 255 hash-length blocks or protocol-required salt, input material, or `info` context is absent or misbound. Record hash, output length, and context identifier, but never PRK, OKM, secret salt, or input keying material.

## Canonical sources

- [RFC 5869](https://www.rfc-editor.org/rfc/rfc5869)
