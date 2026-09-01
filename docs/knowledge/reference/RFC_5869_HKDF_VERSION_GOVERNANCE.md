# RFC 5869 HKDF Version Governance

## Purpose

RFC 5869, *HMAC-based Extract-and-Expand Key Derivation Function (HKDF)* (May 2010), defines a two-stage key-derivation function built on HMAC: an Extract step that condenses input keying material into a pseudorandom key, and an Expand step that produces one or more cryptographic keys of the desired length. HKDF is widely used to derive per-purpose keys from a high-entropy input, including in TLS 1.3 exporters, Noise protocol suites, and many application-layer key derivation schemes.

Implementations that derive keys with HKDF should cite RFC 5869 explicitly, record the hash function and the salt/info separation rules, and avoid using HKDF as a substitute for password-based key derivation.

## Current context and source status

RFC 5869 was published in May 2010 as an Informational RFC and is not updated or obsoleted. It builds on RFC 2104 (HMAC) and is the IETF profile of a construction originally analyzed in the cryptographic literature. Subsequent specifications (for example RFC 8446 for TLS 1.3 and RFC 9380 for hash-to-curve) reuse HKDF with specific info-context strings.

## Governance pattern

1. Cite RFC 5869 explicitly and identify the hash function used (typically HMAC-SHA-256 or HMAC-SHA-384). HKDF is a generic construction; the security bound depends on the underlying HMAC.
2. Record the salt value used in the Extract step. RFC 5869 specifies that a salt is not required but is recommended; a missing salt is recorded as an explicit configuration.
3. Record the info value used in the Expand step. Per-protocol profiles define info strings (for example "tls13 " + label + context) and should be cited together with RFC 5869.
4. Ensure that the Extract step is used when the input keying material is not already a uniform random bit string. Skipping Extract on weak input reduces the security bound.
5. For long output lengths, use the T(1) || T(2) || ... pattern as defined in RFC 5869. Do not exceed the per-block length without iterating.
6. Maintain context separation by binding distinct info strings to distinct derivation purposes. Reusing info across purposes collapses the derived-key separation.
7. For password-based inputs, do not substitute HKDF for a memory-hard KDF such as Argon2id or scrypt. HKDF is suitable only for high-entropy input.
8. Test against the published test vectors from RFC 5869 (Appendix A) and against any per-protocol vectors (for example the TLS 1.3 exporters in RFC 8446).

## Validation and evidence

Evidence includes:

- HKDF algorithm identifier, hash function, and library/version recorded in the cryptographic module's policy;
- salt handling (present, absent, or fixed) documented;
- info strings enumerated for each derivation purpose;
- output length and per-block iteration rules documented;
- positive and negative test vectors from RFC 5869 reproduced by the implementation;
- context-separation rules verified for each protocol using HKDF.

## Failure correction

Common defects include:

- Using HKDF on a low-entropy input (such as a password) instead of a memory-hard KDF, defeating the security bound.
- Skipping the Extract step by passing the input directly to Expand, which assumes the input already has the entropy of the output key length.
- Reusing the same info string across protocols or purposes, collapsing the derived-key separation.
- Truncating the output to a length not justified by the security bound of the underlying HMAC.

Corrective actions include adding a memory-hard KDF for password input, restoring the Extract step, splitting info strings by context, and re-keying to new derivation outputs.

## Limitations

RFC 5869 does not define:

- password-based key derivation; this is intentionally outside the scope;
- post-quantum security; HKDF inherits the HMAC's preimage and pseudo-randomness properties;
- the per-protocol info strings used in TLS 1.3, Noise, or other layered protocols.

HKDF is a key-derivation function, not a key exchange, a MAC, or a cipher.

## Info-string discipline

The info string passed to HKDF Expand is the primary mechanism for context separation. Each distinct purpose should have a distinct info string; reusing the same string across purposes collapses the security bound. Common patterns include:

- TLS 1.3 exporters: `"tls13 " || label || 0x00 || context`, with the label drawn from the IANA TLS Exporter Label registry.
- Noise protocol suites: a fixed info string derived from the protocol name and pattern.
- Application-layer schemes: a self-describing info string with a version and a domain tag, for example `"myapp/v1/key-encryption"`.

A change in the info string is a cryptographic change, not a configuration change. Implementations should version the info strings explicitly and treat changes as protocol-level changes requiring new test vectors.

## Memory-hard alternatives for low-entropy input

RFC 5869's HKDF assumes high-entropy input. For low-entropy input such as a user password, the appropriate construction is a memory-hard KDF: Argon2id (RFC 9106), scrypt (RFC 7914), or PBKDF2 (RFC 8018). PBKDF2 has the longest deployment history but is not memory-hard; Argon2id is the current default for new deployments. Implementations should not use HKDF to derive keys from passwords, because the security bound collapses with low-entropy input.

## Canonical sources

- RFC 5869, *HMAC-based Extract-and-Expand Key Derivation Function (HKDF)* (RFC Editor): https://www.rfc-editor.org/rfc/rfc5869
- RFC 8446, *The Transport Layer Security (TLS) Protocol Version 1.3* (RFC Editor, for HKDF context strings and exporters): https://www.rfc-editor.org/rfc/rfc8446
- NIST SP 800-108, *Recommendation for Key Derivation Using Pseudorandom Functions* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/108/upd1/final

Sources were verified on September 1, 2026.
