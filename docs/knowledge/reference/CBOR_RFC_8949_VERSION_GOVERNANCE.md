---
title: CBOR Version Governance (RFC 8949, RFC 9052, RFC 9053, RFC 9165)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: IETF RFC 8949 (December 2020); RFC 9052 (August 2022); RFC 9053 (August 2022); RFC 9054 (August 2022); RFC 9165 (December 2021); https://www.rfc-editor.org/rfc/rfc8949
---

# CBOR Version Governance (RFC 8949, RFC 9052, RFC 9053, RFC 9165)

## Scope

This card governs how `orchords-docs` evaluates Concise Binary Object Representation (CBOR) and its supporting cryptography / serialization standards. CBOR is the binary data format for constrained environments, IoT, WebAuthn, COSE-secure messaging, and many SD-JWT-based identity tokens.

## Why this card exists

CBOR is a typed binary format with explicit support for tags (RFC 8949 § 3.4), canonicalization (RFC 8949 § 4), and indefinite-length items. COSE (RFC 9052/9053/9054) provides authenticated encryption and signing on top of CBOR. CWT (RFC 8392) provides a CBOR-equivalent of JWT for constrained environments. CIRA (RFC 9165) adds CBOR-in-HTTP header for content negotiation. A KB card that cites "CBOR" without enumerating these standards produces a binary pipeline that cannot interop with the canonical representation.

## Document set

- **RFC 8949** — Concise Binary Object Representation (CBOR) — December 2020.
- **RFC 9052** — CBOR Object Signing and Encryption (COSE) Structure — August 2022.
- **RFC 9053** — CBOR Object Signing and Encryption (COSE) Algorithms — August 2022.
- **RFC 9054** — CBOR Object Signing and Encryption (COSE) Key — August 2022.
- **RFC 8392** — CBOR Web Token (CWT) — May 2018.
- **RFC 8742** — Concise Data Definition Language (CDDL) — April 2020.
- **RFC 9165** — CBOR Encoding for HTTP — December 2021.

References: `https://www.rfc-editor.org/rfc/rfc8949`, `https://www.rfc-editor.org/rfc/rfc9052`, `https://www.rfc-editor.org/rfc/rfc9165`.

## Major type table

CBOR major types are the basis of the typed binary format:

| Major type | Meaning | Example |
|---|---|---|
| 0 | unsigned integer | `1`, `42`, `2^64-1` |
| 1 | negative integer | `-1`, `-42` |
| 2 | byte string | `h'0123'` |
| 3 | text string | `"hello"` |
| 4 | array | `[1, 2, 3]` |
| 5 | map | `{1: "a", 2: "b"}` |
| 6 | tagged item | tag wrapper |
| 7 | floating-point / simple | `1.5`, `true`, `false`, `null`, `undefined` |

## Tag table (RFC 8949 § 3.4)

Tags are critical for interop. The KB reference card enumerates the tags in use. The standard tag set:

| Tag | Meaning |
|---|---|
| 0 | Standard date/time (RFC 3339) |
| 1 | Epoch-based date/time |
| 2 | Positive bignum |
| 3 | Negative bignum |
| 4 | Decimal fraction |
| 5 | Bigfloat |
| 6-11 | reserved (was proposed for bytes/text/arrays/maps) |
| 12 | COSE_Encrypt0 (RFC 9052) |
| 13 | COSE_Mac0 (RFC 9052) |
| 14 | COSE_Sign1 (RFC 9052) |
| 15 | COSE_Encrypt (RFC 9052) |
| 16 | COSE_Mac (RFC 9052) |
| 17 | COSE_Sign (RFC 9052) |
| 18 | COSE_Key (RFC 9052) |
| 22 | COSE_KeySet (RFC 9052) |
| 24 | COSE_Encrypt_tag (RFC 9052) |
| 25 | COSE_Mac_tag (RFC 9052) |
| 26 | COSE_Sign_tag (RFC 9052) |
| 28 | CWT (RFC 8392) |
| 61 | COSE_ToBeSigned |
| 96-127 | IANA-registered |
| 256-32767 | first-party private |

## Canonicalization (RFC 8949 § 4.2)

The CBOR canonical encoding is mandatory for deterministic signature input:

- Maps: keys sorted by encoded length, then by lexicographic byte order.
- Indefinite-length items: forbidden in canonical encoding (use definite-length).
- Numeric encoding: integer form preferred over float form for integer values.
- Tags: included for tagged items.

A reference card that cites "COSE-signed CBOR" must use canonical encoding.

## COSE algorithms (RFC 9053)

The COSE algorithm registry defines:

| Algorithm | Identifier | Use case |
|---|---|---|
| ES256 | -7 | ECDSA P-256 SHA-256 |
| EdDSA | -8 | Ed25519 (preferred) |
| ES384 | -35 | ECDSA P-384 |
| ES512 | -36 | ECDSA P-521 |
| HS256 | 5 | HMAC-SHA-256 |
| HS384 | 6 | HMAC-SHA-384 |
| HS512 | 7 | HMAC-SHA-512 |
| A128GCM | 1 | AES-128-GCM |
| A192GCM | 3 | AES-192-GCM |
| A256GCM | 2 | AES-256-GCM |
| ChaCha20/Poly1305 | 24 | ChaCha20-Poly1305 |
| A128CBC-HS256 | 14 | AES-128-CBC + HMAC-SHA-256 |
| A256CBC-HS512 | 19 | AES-256-CBC + HMAC-SHA-512 |
| ES256K | -47 | ECDSA secp256k1 |

Policy:

- EdDSA (Ed25519) preferred for new deployments.
- ES256 acceptable for ECDSA-required interop.
- AES-CBC allowed only when paired with HMAC (AEAD construction).
- HS256/384/512 only for symmetric use cases.

References: `https://www.iana.org/assignments/cose/cose.xhtml`.

## CWT (RFC 8392)

CBOR Web Token mirrors JWT claims. Mandatory claims:

| Claim | CBOR key | Type |
|---|---|---|
| `iss` | 1 | text |
| `sub` | 2 | text |
| `aud` | 3 | text |
| `exp` | 4 | int (epoch) |
| `nbf` | 5 | int (epoch) |
| `iat` | 6 | int (epoch) |
| `cti` | 7 | bytes (CWT ID) |

CWT is signed with COSE_Sign1 (tag 18 wrapping COSE_Sign1-tagged structure).

## CBOR in HTTP (RFC 9165)

RFC 9165 standardizes CBOR as an HTTP content type:

- Content-Type: `application/cbor`.
- Accept header: `application/cbor`.
- Trailer support: yes (chunked transfer).
- Status codes: HTTP standard codes apply.

## Mandatory pre-flight (before adopting a CBOR-based protocol)

1. CBOR encoder library supports canonical encoding (RFC 8949 § 4.2).
2. Tag set is enumerated and registered.
3. COSE algorithm choice per policy table.
4. CDDL schema is published (RFC 8742).
5. Round-trip and determinism tests pass.

## Sources

- RFC 8949 (CBOR): `https://www.rfc-editor.org/rfc/rfc8949`
- RFC 9052 (COSE Structure): `https://www.rfc-editor.org/rfc/rfc9052`
- RFC 9053 (COSE Algorithms): `https://www.rfc-editor.org/rfc/rfc9053`
- RFC 9054 (COSE Key): `https://www.rfc-editor.org/rfc/rfc9054`
- RFC 8392 (CWT): `https://www.rfc-editor.org/rfc/rfc8392`
- RFC 8742 (CDDL): `https://www.rfc-editor.org/rfc/rfc8742`
- RFC 9165 (CBOR in HTTP): `https://www.rfc-editor.org/rfc/rfc9165`
- IANA COSE registry: `https://www.iana.org/assignments/cose/cose.xhtml`
