# RFC 2104 HMAC Version Governance

## Purpose

RFC 2104, *HMAC: Keyed-Hashing for Message Authentication* (February 1997), defines the Hash-based Message Authentication Code (HMAC) construction. HMAC is a generic MAC built on top of an iterated cryptographic hash function and is used wherever message integrity and authenticity are required from a single primitive, including TLS, IPsec, SSH, JSON Web Signature, and many API authentication schemes.

Protocols and modules that advertise HMAC support should cite RFC 2104 explicitly. Because RFC 2104 is an Informational RFC that does not mandate a specific hash function, a claim of "RFC 2104" must be paired with the hash function and the key-management rules used. RFC 2104 has been updated (not obsoleted) by RFC 6151, which adds security guidance in light of attacks on MD5.

## Current context and source status

RFC 2104 was published in February 1997 and is an Informational RFC. The hash-function family is intentionally a parameter; FIPS 198-1 is the U.S. federal profile that binds HMAC to FIPS-approved hash functions. RFC 6151 (March 2011) updates RFC 2104's security considerations to address attacks that broke MD5 and weakened SHA-1, and recommends SHA-256 or stronger.

RFC 2104 remains the structural reference for HMAC; implementations continue to cite it alongside the specific hash function in use (for example HMAC-SHA-256 per RFC 6234).

## Governance pattern

1. Cite RFC 2104 plus the specific hash function and any companion specification (FIPS 198-1, RFC 4231 test vectors, RFC 6234 for SHA-256). Do not cite HMAC without the hash function.
2. Record the key length, the underlying hash output length, and the block size used in the HMAC construction. RFC 2104 specifies that keys longer than the block size are hashed first and that keys shorter than the block size are padded.
3. Implement the constant `ipad` and `opad` derivation exactly as RFC 2104 defines: `ipad = 0x36` repeated to block size and `opad = 0x5C` repeated to block size.
4. Document the verification behavior for variable-length authentication tags. Truncation of MAC output is permitted by RFC 2104, but only when the application records the chosen length and the resulting security bound.
5. For protocols layered on HMAC (for example JWS `HS256`, `HS384`, `HS512`), record the algorithm label, the key derivation rules, and the constant-time comparison rules.
6. Avoid reusing the same HMAC key across multiple algorithms or domains without a documented separation mechanism (a per-context prefix or a KDF).
7. Maintain a documented replacement for any hash function whose collision or preimage resistance is degraded.
8. Use the published test vectors (RFC 4231) for positive and negative testing across implementation languages.

## Validation and evidence

Evidence includes:

- HMAC algorithm identifier, hash function, key length, and tag length recorded in the cryptographic module's policy;
- Known-answer tests covering at least one message, one key shorter than the block size, and one key longer than the block size;
- constant-time comparison tests for tag verification, where applicable;
- documented key-derivation or key-distribution process;
- test vectors from RFC 4231 reproduced by the implementation.

## Failure correction

Common defects include:

- Computing HMAC using the wrong constant values (ipad/opad) or applying the XOR after the key has already been padded inconsistently.
- Using HMAC-MD5 or HMAC-SHA-1 in new protocols despite RFC 6151 security guidance recommending SHA-256 or stronger.
- Comparing tags in non-constant time, exposing a timing side channel.
- Reusing the same HMAC key for two different contexts (for example, signing and authentication) without context separation.

Corrective actions include updating the algorithm to a stronger hash, fixing the constant values against the RFC, switching to constant-time verification, and re-keying the context with separation prefixes.

## Limitations

RFC 2104 does not define:

- the hash function itself; it is a generic construction;
- the security proof, which was supplied in subsequent literature and discussed in the security considerations;
- the per-protocol labels used in JOSE, CMS, or other layered encodings.

It is not a confidentiality mechanism. HMAC alone does not encrypt; it authenticates.

## Use in layered protocols

HMAC is used inside many IETF protocols, each of which defines an algorithm label and an info-binding rule:

- JOSE/JWS uses `HS256`, `HS384`, and `HS512` for HMAC-SHA-256, HMAC-SHA-384, and HMAC-SHA-512.
- TLS 1.2 (RFC 5246) and TLS 1.3 (RFC 8446) use HMAC inside the PRF and HKDF constructions.
- SSH (RFC 4253) uses HMAC-SHA-256 and HMAC-SHA-512 in the binary packet protocol.
- IPsec (RFC 4303) uses HMAC-SHA-256 and HMAC-SHA-384 for integrity.
- S/MIME (RFC 8551) uses HMAC for CMS authenticated-data.

A change in the underlying hash function is not a backwards-compatible change. Implementations should bind the HMAC construction to the protocol identifier and should not negotiate or substitute HMAC variants outside the negotiated profile.

## Migration from MD5 and SHA-1

RFC 6151 (March 2011) updates RFC 2104's security considerations to address attacks that broke MD5's collision resistance and weakened SHA-1's collision resistance. The recommendation is to use SHA-256 or stronger for HMAC. Implementations that still expose HMAC-MD5 or HMAC-SHA-1 should label those variants as legacy, restrict them to backwards-compatibility mode, and migrate to HMAC-SHA-256 or stronger for new protocol bindings.

When a layered protocol negotiates an HMAC variant dynamically, the negotiation should be governed by a policy that records the acceptable hash strengths and that rejects negotiation down to a weaker variant absent an explicit backwards-compatibility flag.

## Canonical sources

- RFC 2104, *HMAC: Keyed-Hashing for Message Authentication* (RFC Editor): https://www.rfc-editor.org/rfc/rfc2104
- RFC 6151, *Updates to RFC 2104: Security Considerations for the MD5 and SHA-1 Hash Functions* (RFC Editor): https://www.rfc-editor.org/rfc/rfc6151
- RFC 4231, *Identifiers and Test Vectors for HMAC-SHA-224, HMAC-SHA-256, HMAC-SHA-384, and HMAC-SHA-512* (RFC Editor): https://www.rfc-editor.org/rfc/rfc4231

Sources were verified on September 1, 2026.
