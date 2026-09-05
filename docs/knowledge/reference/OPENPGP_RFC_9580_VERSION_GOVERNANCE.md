---
title: "OpenPGP (RFC 9580) Version Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 9580 (July 2024); IETF RFC 4880 (November 2007); IETF RFC 6631 (June 2012); https://www.rfc-editor.org/rfc/rfc9580"
---

# OpenPGP (RFC 9580) Version Governance

## Purpose

This card governs how ORCHORDS references the OpenPGP message format, including the July 2024 update (RFC 9580) that integrates the modern AEAD encryption modes, post-quantum hybrid keys, and improved signature algorithms.

## Canonical Reference

- IETF RFC 9580 — *OpenPGP*, July 2024 (obsoletes RFC 4880 in the context of new packet formats; RFC 4880 remains the wire-format reference for legacy keys).
- IETF RFC 6631 — *Suite B Cryptographic Suites for OpenPGP*, June 2012 (legacy ECDH/ECDSA curves).
- IETF RFC 4880bis draft history — Provided the v5 keys and AEAD Encrypted Data packet (later promoted into RFC 9580).
- Implementations: GnuPG 2.4+, Sequoia-PGP, RNP, OpenKeychain.

## Core Properties

- **Packet-based binary format** — Every OpenPGP message is a sequence of self-describing packets (Public-Key, Secret-Key, User ID, Signature, Public/Private Subkey, Literal Data, Compressed Data, AEAD Encrypted Data, Sym. Encrypted Integrity Protected Data, Marker, etc.).
- **Two-tier key model** — Primary signing key + subkeys for encryption and authentication. Each subkey can have its own algorithm and expiry.
- **Trust model** — OpenPGP uses a *web of trust* rather than a single-rooted PKI: trust is signed by other OpenPGP users and propagated. This is distinct from X.509 / S/MIME and is the most operationally different aspect of OpenPGP.
- **S2K (string-to-key)** — Iterated and salted S2K protects private keys at rest; RFC 9580 §3.7 requires Argon2id as the modern S2K.
- **AEAD encryption** — RFC 9580 §5.16 introduces AEAD Encrypted Data packet (tag 20), supporting OCB, EAX, and GCM modes. Replaces the older CFB-encrypted Symmetrically Encrypted Integrity Protected Data packet (tag 18) for new implementations.
- **Hash algorithms** — SHA-256/384/512 are recommended; SHA-1 retained only for verifying legacy signatures; MD5 disallowed for any new use.
- **Public-key algorithms** — EdDSA (Ed25519, Ed448) and ECDSA (P-256, P-384, P-521); RSA up to 4096 bits is acceptable; DSA disallowed.

## Migration and Version Drift (RFC 4880 → RFC 9580)

| Element | RFC 4880 (legacy) | RFC 9580 (current) | Notes |
| --- | --- | --- | --- |
| Key version | v3 (signing only), v4 | v4 (existing), v6 (new) | v5 was never published; v6 introduces S2K count and usage flags reformatting. |
| Symmetric cipher | AES-128/256 CFB | AES-128/256 OCB (AEAD), GCM (AEAD), EAX (AEAD) | AEAD replaces CFB everywhere except legacy backward compatibility. |
| S2K | Iterated+salted SHA-1 | Argon2id (recommended), iterated+salted SHA-256 (acceptable) | Argon2id mandatory for new secrets. |
| Hash for fingerprint | SHA-1 (v4 keys) | SHA-256 (v6 keys) | v6 fingerprints are 256 bits. |
| ECC curves | NIST P-256/384/521, Brainpool, Curve25519 (legacy) | Curve25519, Curve448, Ed25519, Ed448, NIST P-256/384/521 | Curve25519 / Ed25519 are the modern default. |
| Post-quantum | none | ML-KEM-768 + X25519 hybrid, ML-KEM-1024 + X448 hybrid, ML-DSA-65/87, SLH-DSA-128s/f, Ed448 (FIPS 204/205) | New public-key algorithm IDs 25–29. |
| Signature types | binary over hashed subpackets | same; v6 keys may use SHA-3-256 | backward-compatible signature packets. |
| Revocation signature | separate self-sig | same | v6 introduces "intended-recipient" subpacket for more granular revocation distribution. |

## Usage in ORCHORDS

- For new OpenPGP keys, generate v6 keys with Curve25519/Ed25519 and Argon2id S2K.
- When integrating with partners who have not migrated, signing or verifying v4 keys remains acceptable — RFC 9580 mandates backward-read compatibility for v4.
- For post-quantum readiness in long-archive scenarios (e.g., signed legal documents, source code signing for >10-year retention), prefer v6 keys with ML-DSA-65 or hybrid Ed25519+ML-DSA-65 signatures.
- Treat RFC 9580 fingerprint migration (SHA-256) as an opportunity to rekey rather than a hard compatibility break — keep an SHA-1 fingerprint mapping if WKD/HSM discovery requires it.

## Open Items

- Track vendor support for v6 keys: GnuPG 2.4+ has experimental v6; Sequoia-PGP has fuller coverage.
- Monitor RFC 9580 errata (still active as of 2026-09-05; one known issue around Ed448+Argon2 combinations).
- Re-evaluate the OpenPGP web-of-trust model in favour of WKD (Web Key Directory) + certificate transparency-style key transparency logs for new deployments.
