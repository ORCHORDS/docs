# FIPS 198-1 Keyed-Hash Message Authentication Code (HMAC) Version Governance

## Purpose

FIPS 198-1, *The Keyed-Hash Message Authentication Code (HMAC)* (approved July 2008), is the U.S. federal standard for HMAC. It is the FIPS-validated profile of the RFC 2104 construction, binding HMAC to FIPS-approved hash functions (initially SHA-1, SHA-224, SHA-256, SHA-384, SHA-512). FIPS 198-1 specifies the keyed-hash construction, the ipad/opad constants, and the block-size handling that implementations must follow when claiming FIPS validation.

Profiles that claim FIPS 198-1 conformance should cite FIPS 198-1 explicitly and the companion FIPS 180 (Secure Hash Standard) or FIPS 202 (SHA-3) for the underlying hash function.

## Current context and source status

FIPS 198-1 was approved on July 11, 2008, and supersedes FIPS 198 (March 2002). It is currently the FIPS standard for HMAC. NIST SP 800-107 (now updated as SP 800-107 Rev. 1) provides security guidance for the FIPS-approved hash functions in HMAC. SP 800-131A Rev. 2 maps assurance labels (deprecated, restricted, acceptable, legacy) onto HMAC-SHA-1, HMAC-SHA-224, HMAC-SHA-256, HMAC-SHA-384, HMAC-SHA-512.

## Governance pattern

1. Cite FIPS 198-1 and identify the underlying hash function (SHA-1, SHA-224, SHA-256, SHA-384, SHA-512). Do not cite FIPS 198-1 without naming the hash function.
2. Record the FIPS 140 validation status of the cryptographic module that performs HMAC. FIPS 198-1 conformance relies on a FIPS-validated module.
3. Document the key length and the block-size handling. FIPS 198-1 specifies that keys longer than the hash function's block size are hashed first and that shorter keys are padded to the block size.
4. Apply the assurance labels from SP 800-131A Rev. 2. HMAC-SHA-1 is labeled "legacy"; HMAC-SHA-224 is "acceptable"; HMAC-SHA-256, HMAC-SHA-384, and HMAC-SHA-512 are "acceptable" with HMAC-SHA-256 being the typical default.
5. Use FIPS 198-1's test vectors (Appendix A and the CAVP test vectors) for conformance testing.
6. Document the constant-time comparison for tag verification.
7. For layered protocols (TLS 1.2 HMAC suite, JWS HS256/384/512), record the protocol-specific label and the test vectors from that protocol.
8. Where HMAC is used in conjunction with a key derivation function (for example HKDF from RFC 5869), record the KDF construction and the boundary between KDF output and HMAC key.

## Validation and evidence

Evidence includes:

- the HMAC algorithm identifier and the FIPS-approved hash function recorded in the cryptographic module's policy;
- FIPS 140 certificate number and security policy reference;
- test vectors from FIPS 198-1 and CAVP reproduced by the implementation;
- constant-time tag verification tests;
- protocol-specific test vectors for the integrating protocol.

## Failure correction

Common defects include:

- Claiming FIPS 198-1 conformance while using a hash function that FIPS 198-1 does not bind, such as MD5.
- Failing to follow the FIPS 198-1 block-size handling (keys longer than the block size should be hashed, not truncated).
- Labeling the implementation as FIPS-validated while the underlying module is not FIPS 140-validated.
- Using HMAC-SHA-1 in new protocols despite its "legacy" label.

Corrective actions include re-binding the implementation to an acceptable hash function, fixing the key handling, re-validating under FIPS 140, and migrating to HMAC-SHA-256 or stronger where applicable.

## Limitations

FIPS 198-1 does not define:

- the underlying hash functions (governed by FIPS 180 / FIPS 202);
- key derivation or key management (governed by SP 800-57 Part 1 Rev. 5);
- a confidentiality mechanism; HMAC is authentication, not encryption.

The publication is not itself a module validation; it is the algorithm standard used as input to FIPS 140 module validation.

## Cross-references and operational guidance

FIPS 198-1 is widely cited together with NIST SP 800-107 Rev. 1, which provides per-hash-function security guidance including expected collision and preimage resistance strengths. New deployments should align the HMAC implementation with the assurance labels in SP 800-131A Rev. 2 and with the secure-hash guidance in SP 800-107 Rev. 1.

Where HMAC is used as a pseudo-random function (for example in HKDF), the HMAC key must be treated as a keying material under SP 800-57 Part 1 Rev. 5, including originator-usage and recipient-usage periods. The HMAC key must not be reused as an input key to a separate KDF unless an explicit separation mechanism is in place, because doing so collapses the cryptographic context boundaries the two functions are designed to enforce.

## Module validation expectations

A FIPS 140-validated module that supports FIPS 198-1 must list the supported hash functions in its security policy, must include HMAC in the CAVP (NIST CAVS) test evidence, and must operate the HMAC primitive only through the validated module boundary. Implementations that perform HMAC outside the module boundary, or that expose the HMAC primitive as a wrapper around a non-validated hash, do not satisfy FIPS 198-1 conformance regardless of how the algorithm is computed.

## Canonical sources

- FIPS 198-1, *The Keyed-Hash Message Authentication Code (HMAC)* (NIST CSRC): https://csrc.nist.gov/pubs/fips/198-1/final
- NIST SP 800-131A Rev. 2, *Transitioning the Use of Cryptographic Algorithms and Key Lengths* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/131/a/r2/final
- NIST SP 800-107 Rev. 1, *Recommendation for Applications Using Approved Hash Algorithms* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/107/r1/final

Sources were verified on September 1, 2026.
