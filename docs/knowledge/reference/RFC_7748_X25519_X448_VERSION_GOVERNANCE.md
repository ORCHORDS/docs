# RFC 7748 X25519 and X448 Version Governance

## Purpose

RFC 7748, *Elliptic Curves for Security* (January 2016), specifies the Montgomery curves curve25519 and curve448 and the Diffie-Hellman functions X25519 and X448 built on them. X25519 is the dominant TLS 1.3 key-exchange group and the default ephemeral DH in modern protocols.

Implementations using X25519/X448 should cite RFC 7748 explicitly, record the group selection and clamping behavior, and enforce the standard's contributory-input validation rules.

## Current context and source status

RFC 7748 was published January 2016 as an Informational RFC and is not updated or obsoleted in force. TLS 1.3 (RFC 8446) adopts X25519 as group 0x001d and X448 as 0x001e. RFC 9180's HPKE defines DHKEM(X25519, HKDF-SHA256) as ciphersuite identifier 0x0020. Hybrid post-quantum constructions (X25519MLKEM768, draft-ietf-tls-ecdhe-mlkem) layer ML-KEM over X25519 while retaining RFC 7748 mechanics for the classical component.

## Governance pattern

1. Cite RFC 7748 and record the function (X25519 or X448) and its protocol mapping (TLS group identifier, HPKE KEM identifier).
2. Use a conformant implementation of the Montgomery ladder; do not reimplement — constant-time ladder implementations are subtle and the failure mode is private-key recovery.
3. Apply the standard's scalar clamping as part of the function; clamping bits are part of X25519's definition and security analysis.
4. Generate private keys with a uniform random 32-byte (X25519) or 56-byte (X448) seed from an approved DRBG.
5. Validate peer public keys per protocol rules: RFC 7748 permits skipping all-zero checks where the protocol's KDF provides contributory behavior (TLS 1.3 does), but low-order-point validation must not be "helpfully" added in ways that break conformance; follow the protocol profile, not ad-hoc checks.
6. Ephemeral use is the default: generate a fresh key pair per exchange where the protocol specifies ephemeral DH; static X25519 use requires protocol-level design (HPKE receiver keys) and rotation.
7. Track the hybrid migration: post-quantum hybrids retain X25519 as the classical leg; group identifiers and negotiation are protocol-layer concerns — record which groups the service negotiates and why.
8. Reproduce the RFC 7748 test vectors (Sections 5.2 and 6.2) before production use.

## Validation and evidence

Evidence includes:

- function and protocol identifier mapping recorded per service;
- implementation library and version with constant-time claims recorded;
- key generation source (approved DRBG) documented;
- peer-key validation decision traced to the protocol profile;
- ephemeral vs static usage and rotation policy;
- RFC 7748 test vectors reproduced.

## Failure correction

Common defects include:

- Hand-rolled Montgomery ladders with timing leaks.
- Ad-hoc public-key validation rejecting valid low-order-contributing points or accepting all-zero outputs where the protocol profile forbids the check's absence.
- Static X25519 keys reused across exchanges without a protocol that supports static modes.
- Clamping skipped or double-applied by wrapper layers.

Corrective actions include adopting a vetted library, aligning validation with the protocol specification, rotating static keys, and removing wrapper-layer scalar manipulation.

## Limitations

RFC 7748 does not define:

- signatures on these curves; Ed25519/Ed448 are RFC 8032's scope;
- post-quantum security; the classical leg of hybrids must be paired with ML-KEM per the hybrid specifications;
- key derivation; the shared secret feeds a KDF per protocol.

X25519/X448 are Diffie-Hellman functions, not signature schemes or KDFs.

## Low-order point handling

The all-zero shared-secret check is deliberately absent from X25519's definition; whether to test for it belongs to the protocol layer. TLS 1.3's HKDF-based key schedule provides contributory behavior by construction, so the check is unnecessary there and non-conformant additions risk interop failures. Static-recipient protocols (HPKE) specify their own validation requirements. Follow the consuming protocol's text precisely.

## Canonical sources

- RFC 7748, *Elliptic Curves for Security* (RFC Editor): https://www.rfc-editor.org/rfc/rfc7748
- RFC 8446, *The Transport Layer Security (TLS) Protocol Version 1.3* (group registration): https://www.rfc-editor.org/rfc/rfc8446
- RFC 9180, *Hybrid Public Key Encryption* (DHKEM usage): https://www.rfc-editor.org/rfc/rfc9180
- RFC 8032, *Edwards-Curve Digital Signature Algorithms (EdDSA)* (companion signatures): https://www.rfc-editor.org/rfc/rfc8032
- IANA — TLS Supported Groups registry: https://www.iana.org/assignments/tls-parameters/

Sources were verified on September 2, 2026.
