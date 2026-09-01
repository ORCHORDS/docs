# ISO/IEC 9796-2 Digital Signatures with Appendix Version Governance

## Purpose

ISO/IEC 9796-2, *Information technology — Security techniques — Digital signature schemes giving message recovery — Part 2: Integer factorization based mechanisms*, defines digital signature schemes that recover part or all of the message from the signature itself. The most widely deployed profile is RSA-based with the EMSA-PKCS1-v1_5 padding style specified in the publication. The standard covers RSA with both plain and randomized hash functions, and is used in applications such as EMV (chip-card payments), digital tachographs, and certain government-identity documents.

Profiles that claim ISO/IEC 9796-2 conformance should cite the specific edition, identify the padding variant in use, and bind the signature scheme to the underlying RSA key length and the hash function.

## Current context and source status

ISO/IEC 9796-2 has multiple editions: the 2002 first edition introduced EMSA-PKCS1-v1_5 and EMSA-PSS; the 2010 second edition refined the message-recovery mechanism and clarified the security proofs; and the standard has been amended to address attacks on earlier EMSA-PKCS1-v1_5 padding (Bleichenbacher-style attacks). Implementations should cite the edition in force and the amendment status.

The publication is international and is referenced by national profiles (BSI TR-02102-1, NIST FIPS 186-5 for RSA, and EMVCo specifications for chip cards).

## Governance pattern

1. Cite the specific ISO/IEC 9796-2 edition and any amendment (for example ISO/IEC 9796-2:2010 with amendment 1).
2. Identify the padding scheme in use: EMSA-PKCS1-v1_5 or EMSA-PSS. The two schemes have different security arguments and different vulnerability profiles.
3. Record the underlying RSA modulus size and the hash function. The standard allows modular sizes from 1024 bits upward; current profiles require at least 2048 bits and deprecate 1024.
4. Apply the message-recovery bound. The signature scheme can recover part of the message from the signature; if the entire message is recovered, the recovered bytes must be verified against the original message and not used as the primary verification path.
5. Document the encoding rules: the DER encoding of the DigestInfo, the hash algorithm identifier, and the position of the recovered bytes within the signature.
6. Where the publication is used in combination with FIPS 186-5, ensure the FIPS-validated signature path is the active path. ISO/IEC 9796-2 by itself is not a FIPS validation.
7. Test against the ISO/IEC 9796-2 test vectors and against the FIPS 186-5 RSA test vectors.
8. Maintain awareness of historical attacks on EMSA-PKCS1-v1_5 (Bleichenbacher's signature forgery with low public exponents) and the published countermeasures. Implementations should verify that the verification path rejects forgeries with malformed DigestInfo.

## Validation and evidence

Evidence includes:

- the ISO/IEC 9796-2 edition and padding scheme recorded in the cryptographic policy;
- the RSA modulus size, public exponent, and hash function recorded;
- the message-recovery length and the verification path documented;
- FIPS 186-5 evidence where FIPS validation is also claimed;
- test vectors from ISO/IEC 9796-2 and FIPS 186-5 reproduced by the implementation;
- verification-path tests rejecting malformed DigestInfo and excessive recoverable bytes.

## Failure correction

Common defects include:

- Using ISO/IEC 9796-2's EMSA-PKCS1-v1_5 padding without implementing the verification rules that defend against the Bleichenbacher low-exponent forgery.
- Recovering the entire message from the signature without comparing it to the original, allowing a single-bit error to propagate silently.
- Citing ISO/IEC 9796-2 for FIPS validation, which is the role of FIPS 186-5.
- Using a 1024-bit RSA modulus in new applications despite current profile guidance.

Corrective actions include re-implementing the verification path with strict DigestInfo parsing, restoring the message comparison, aligning with FIPS 186-5 where FIPS validation is required, and migrating to at least 2048-bit RSA.

## Limitations

ISO/IEC 9796-2 does not define:

- the underlying RSA primitive (governed by FIPS 186-5 and PKCS #1 v2.x);
- digital signature schemes based on elliptic curves (governed by ISO/IEC 9796-3 and FIPS 186-5);
- key management (governed by SP 800-57 Part 1 Rev. 5 and ISO/IEC 11770).

The publication is not itself a FIPS standard; FIPS-validated implementations rely on FIPS 186-5.

## Recovery-byte handling and forgery resistance

ISO/IEC 9796-2 with EMSA-PKCS1-v1_5 has historically been the target of Bleichenbacher-style signature forgery attacks when implementations parsed the DigestInfo structure loosely or when public exponents were unusually small. The 2010 second edition tightened the message-recovery bounds and the verification requirements; current profiles should adopt that binding and reject any signature whose recovered bytes do not exactly match the original message bytes that were signed.

Implementations should also enforce a minimum modulus size (2048 bits or larger), a minimum hash output (SHA-256 or stronger), and an unambiguous encoding of the hash algorithm identifier. Where ISO/IEC 9796-2 is used in chip-card payment systems governed by the EMV specifications, the EMVCo profile imposes additional constraints on transaction data recovery and on the certificate chain; those constraints are layered on top of ISO/IEC 9796-2 and are not a substitute for it.

## Cross-document alignment

Where the publication is used in conjunction with PKCS #1 v2.x (RFC 8017), the EMSA-PKCS1-v1_5 padding should match the PKCS #1 v2.x ASN.1 module, and the DigestInfo structure should be DER-encoded exactly as specified by PKCS #1. Differences in ASN.1 encoding (extra leading zeroes, length misinterpretation, or trailing bytes) cause verification failures or, worse, forgery acceptance; implementations should reject signatures whose DigestInfo is not a strict match.

## Canonical sources

- ISO/IEC 9796-2:2010, *Information technology — Security techniques — Digital signature schemes giving message recovery — Part 2: Integer factorization based mechanisms* (ISO catalogue): https://www.iso.org/standard/56596.html
- NIST FIPS 186-5, *Digital Signature Standard (DSS)* (NIST CSRC): https://csrc.nist.gov/pubs/fips/186/5/final
- NIST SP 800-56B Rev. 2, *Recommendation for Pair-Wise Key-Establishment Schemes Using Integer Factorization Cryptography* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/56/b/r2/final

Sources were verified on September 1, 2026.
