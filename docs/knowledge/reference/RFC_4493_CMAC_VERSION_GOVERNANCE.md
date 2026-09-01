# RFC 4493 AES-CMAC Version Governance

## Purpose

RFC 4493, *The AES-CMAC Algorithm* (June 2006), defines a Cipher-based MAC built on AES-128. CMAC is a NIST-recommended technique for message authentication when a block cipher is preferred over a hash function, and is used in protocols such as EAP-AKA, IEEE 802.16e, and ZIGBEE. The construction provides the same security properties as a hash-based MAC when the underlying cipher is a secure block cipher with a 128-bit block size.

Implementations that claim CMAC support should cite RFC 4493 explicitly and record the AES key length (AES-128 is the original profile), the subkey generation steps, and the tag length in use.

## Current context and source status

RFC 4493 was published in June 2006 and is an Informational RFC. It is not obsoleted. RFC 4493 is independent of RFC 7253 (which updates RFC 4493 to add CMAC mode for other AES key sizes, namely AES-192 and AES-256). Implementations should cite both when AES-192 or AES-256 are used; a bare reference to RFC 4493 implies AES-128.

The construction is also reflected in NIST SP 800-38B, which is the U.S. federal source for the CMAC algorithm.

## Governance pattern

1. Cite RFC 4493 explicitly and, if AES-192 or AES-256 is in scope, also cite RFC 7253 or NIST SP 800-38B.
2. Record the AES key length and the AES block size (always 128 bits). CMAC's security argument depends on the underlying cipher having a 128-bit block.
3. Implement the subkey generation exactly as RFC 4493 specifies: compute L = AES_K(0^128), then K1 = L · x if MSB(L) = 0 else L · x + R_b, and K2 = K1 · x if MSB(K1) = 0 else K1 · x + R_b. The constants are well-documented; re-implementations are a frequent source of defects.
4. Document the handling of the final block: the last block is XORed with K1 if it is complete and with K2 if padding is required. Do not skip the padding rule.
5. Record the tag length. CMAC permits truncation to any length that meets the application's security bound; implementations must store the chosen length explicitly.
6. Use the published test vectors from RFC 4493 for conformance testing across implementation languages.
7. Document the message-length handling for very large messages. CMAC operates on full 128-bit blocks; large messages must be processed in order, and partial blocks must follow the finalization rule.
8. Where CMAC is used inside a higher-level protocol (for example EAP-AKA), record the protocol's tag length, the key-derivation rules, and the verification timing.

## Validation and evidence

Evidence includes:

- AES key length recorded in the cryptographic module's policy;
- subkey generation (K1 and K2) tested against RFC 4493 test vectors;
- final-block tests covering both the complete-block and the padding-required cases;
- tag-length handling for both full-length and truncated tags;
- constant-time comparison tests for verification, where applicable.

## Failure correction

Common defects include:

- Using a constant subkey (for example, a fixed K1, K2) rather than recomputing K1 and K2 from L each time the key changes.
- Skipping the final-block XOR or applying the wrong subkey to the final block.
- Confusing CMAC with CBC-MAC without the CMAC finalization, which is not a secure MAC by itself.
- Tag truncation performed without documenting the security bound.

Corrective actions include re-implementing the subkey generation against the RFC test vectors, applying the correct final-block rule, switching to the documented CMAC construction rather than CBC-MAC, and recording the tag length in the verification path.

## Limitations

RFC 4493 does not define:

- AES-192 or AES-256 CMAC (governed by RFC 7253 or NIST SP 800-38B);
- the security proof, which is described in NIST SP 800-38B and the literature;
- key management or key derivation rules.

CMAC is not a cipher mode for confidentiality; it is a MAC.

## Use in EAP-AKA, IEEE 802.16e, and ZIGBEE

RFC 4493's CMAC is used as the underlying MAC in several protocols. EAP-AKA and EAP-AKA' bind the CMAC key to the authentication vector and use a 128-bit tag; the tag is verified using constant-time comparison. IEEE 802.16e uses CMAC for integrity in privacy-key-management messages, with the CMAC key derived from the AK (authorization key). ZIGBEE uses CMAC for command frames in the trust-center link-key exchange.

Each integrating protocol typically defines its own tag-length, key-derivation, and verification-timing rules. Implementations should cite both RFC 4493 and the integrating protocol specification in the cryptographic policy and should test against the integrating protocol's test vectors, not only against RFC 4493's standalone test vectors.

## Migration to GMAC, HMAC, or KMAC

CMAC is one of several block-cipher-based MACs. Where AES is already in use, GMAC (NIST SP 800-38D) offers similar authentication properties but uses the AES-GCM construction; GMAC is not a drop-in replacement for CMAC and has different nonce requirements. Where a hash function is preferred, HMAC (RFC 2104) or KMAC (SP 800-185) is more appropriate. Implementations should not silently substitute CMAC for HMAC or for GMAC; the substitution must be a protocol-level decision with explicit test-vector coverage.

## Canonical sources

- RFC 4493, *The AES-CMAC Algorithm* (RFC Editor): https://www.rfc-editor.org/rfc/rfc4493
- RFC 7253, *The OCB Authenticated-Encryption Algorithm* and (in its Appendix) *AES-CMAC with AES-192 and AES-256* (RFC Editor): https://www.rfc-editor.org/rfc/rfc7253
- NIST SP 800-38B, *Recommendation for Block Cipher Modes of Operation: The CMAC Mode for Authentication* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/38/b/final

Sources were verified on September 1, 2026.
