# RFC 8439 ChaCha20-Poly1305 AEAD Version Governance

## Purpose

RFC 8439, *ChaCha20 and Poly1305 for IETF Protocols* (June 2018), specifies the ChaCha20 stream cipher, the Poly1305 universal hash function, and the combined ChaCha20-Poly1305 Authenticated Encryption with Associated Data (AEAD) construction. It obsoletes RFC 7539, the earlier IETF profile, and is the IETF standards-track profile used by TLS 1.3 (RFC 8446), SSH (RFC 4253 with chacha20-poly1305@openssh.com), and many application protocols.

Implementations that claim ChaCha20-Poly1305 should cite RFC 8439 explicitly, identify the variant (IETF profile) and the nonce handling, and avoid silently substituting the Bernstein draft profile or RFC 7539 without re-validation.

## Current context and source status

RFC 8439 was published in June 2018 as a Standards Track (Proposed Standard) document and is not updated or obsoleted. It supersedes RFC 7539, which itself was an Information RFC. RFC 8439 corrects the test vectors and clarifies the nonce construction that earlier profiles left ambiguous.

The cipher and authenticator are also referenced in IETF RFC 7539 test vectors and in the older Bernstein chacha20-poly1305 draft, which differ in the order of fields and in the AEAD construction rules. Implementations should use the RFC 8439 profile, not the draft.

## Governance pattern

1. Cite RFC 8439 explicitly. Do not cite "RFC 7539" or "the Bernstein draft" as the current IETF profile.
2. Record the nonce length (96 bits / 12 bytes is the recommended IETF profile; a 64-bit nonce from RFC 7539 is permitted but requires the extended-nonce construction).
3. Record the key length (256 bits / 32 bytes for both ChaCha20 and Poly1305). ChaCha20-Poly1305 does not support shorter keys.
4. Record the AEAD construction: nonce, key, AAD, plaintext, and the 128-bit authentication tag. The order of construction in RFC 8439 is Poly1305(key=Poly1305_clamp(chacha20_block(key, counter=0)[0..32]), message = AAD || plaintext); do not substitute a draft order.
5. Document the nonce uniqueness requirement. The Poly1305 AEAD is catastrophically broken under nonce reuse. Implementations should use a counter or a deterministic construction, never a random nonce drawn from a small space.
6. Use the RFC 8439 test vectors (Appendix A) for conformance testing.
7. Document the integration with TLS 1.3 (RFC 8446 cipher suite identifiers), SSH, and any application protocols, including the protocol-specific counter or sequence-number rules.
8. Where the implementation distinguishes between Poly1305 as a standalone authenticator and the AEAD construction, record both separately and avoid confusing them.

## Validation and evidence

Evidence includes:

- the AEAD identifier, key length, and nonce length recorded in the cryptographic module's policy;
- the AEAD construction order documented and tested against the RFC 8439 test vectors;
- nonce-handling tests (counter mode, deterministic mode, and rejection of duplicate nonces);
- AAD handling tests covering empty, short, and large associated data;
- tag verification timing and constant-time comparison rules;
- cross-protocol evidence for TLS 1.3 and SSH where applicable.

## Failure correction

Common defects include:

- Generating random 96-bit nonces where the implementation cannot guarantee uniqueness, enabling catastrophic forgery under nonce reuse.
- Substituting the RFC 7539 test vectors or the Bernstein draft test vectors without re-validating against RFC 8439.
- Mixing the Poly1305 standalone authenticator with a different cipher, then labeling the result ChaCha20-Poly1305.
- Confusing the AEAD construction with the underlying ChaCha20 stream cipher, treating it as a confidentiality-only primitive.

Corrective actions include switching to a counter or deterministic nonce, re-running the test vectors from RFC 8439 Appendix A, separating the Poly1305 standalone authenticator from the AEAD construction, and adding the AAD and tag verification rules to the protocol layer.

## Limitations

RFC 8439 does not define:

- key management or key derivation (governed by the integrating protocol such as TLS 1.3);
- confidentiality without authentication (it is an AEAD construction);
- post-quantum security.

The cipher and authenticator are not a substitute for digital signatures.

## Use in TLS 1.3 and SSH

In TLS 1.3 (RFC 8446), the cipher suite identifiers are `TLS_CHACHA20_POLY1305_SHA256` (mandatory-to-implement for non-AES platforms) and `TLS_CHACHA20_POLY1305_SHA256_OLD` (retained for compatibility). The TLS 1.3 record layer uses AEAD with an 8-byte explicit nonce drawn from the record sequence counter; the nonce is appended to the per-record IV to form the AEAD nonce. Implementations should ensure that the sequence counter is not reset on key rotation in a way that re-uses an old nonce, and that the AEAD construction is exactly the IETF profile.

In SSH (RFC 4253 with the chacha20-poly1305@openssh.com extension), the AEAD is applied to the binary packet protocol's per-packet sequence number. The nonce is constructed as the 64-bit sequence number in network byte order. Implementations should verify the construction order (Poly1305 key derivation before message processing) matches the OpenSSH extension, not the earlier chacha20-poly1305 draft.

## Comparison with AES-GCM

ChaCha20-Poly1305 is often deployed alongside AES-256-GCM as a software-friendly AEAD. AES-GCM requires hardware acceleration (AES-NI, ARMv8 Cryptographic Extensions) for high performance; ChaCha20-Poly1305 is constant-time on platforms without those extensions and is widely used on mobile and embedded platforms. Implementations that choose ChaCha20-Poly1305 for performance reasons should record the platform rationale and should not silently switch to AES-GCM, because the AEAD constructions have different nonce-derivation rules.

## Canonical sources

- RFC 8439, *ChaCha20 and Poly1305 for IETF Protocols* (RFC Editor): https://www.rfc-editor.org/rfc/rfc8439
- RFC 7539 (obsoleted), *ChaCha20 and Poly1305 for IETF Protocols* (RFC Editor, retained for history): https://www.rfc-editor.org/rfc/rfc7539
- RFC 8446, *The Transport Layer Security (TLS) Protocol Version 1.3* (RFC Editor, for cipher suite identifiers): https://www.rfc-editor.org/rfc/rfc8446

Sources were verified on September 1, 2026.
