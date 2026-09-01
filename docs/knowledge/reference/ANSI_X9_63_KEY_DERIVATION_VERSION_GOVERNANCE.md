# ANSI X9.63 Key Derivation Function Version Governance

## Purpose

ANSI X9.63, *Public Key Cryptography for the Financial Services Industry — Key Agreement and Key Transport Using Elliptic Curve Cryptography*, is an industry standard from the American National Standards Institute's X9 financial-services committee. It defines elliptic-curve Diffie-Hellman key agreement and an X9.63 Key Derivation Function (KDF) that produces symmetric keys from a shared secret produced by an ECDH primitive. The KDF has been incorporated into other standards (for example IEEE 1363a, SEC 1) and into IETF protocols that pre-date the explicit use of SP 800-56A's KDF.

Implementations that claim X9.63 key derivation should cite the version of X9.63 in scope, distinguish the X9.63 KDF from SP 800-56A Rev. 3's KDF, and document the shared secret encoding.

## Current context and source status

The X9.63 standard has been revised over time; X9.63-2011 is a widely referenced version for the KDF construction, and the standard has been incorporated into subsequent industry profiles. The X9.63 KDF construction is also documented in SEC 1 (Standards for Efficient Cryptography Group) as a compatible KDF. Newer implementations typically use SP 800-56A Rev. 3's KDF instead of X9.63, but X9.63 remains an authoritative source for legacy interoperability.

## Governance pattern

1. Cite the specific X9.63 version (for example X9.63-2011) when claiming X9.63 KDF conformance. Do not cite X9.63 without the version.
2. Record the shared secret format: the concatenation of the x-coordinate of the ECDH shared point, with no zero-padding and a fixed length.
3. Document the key-derivation data passed to the KDF, including any shared-info string and the encoding rules.
4. Use the X9.63 KDF construction: a hash function (SHA-256, SHA-384, or SHA-512) iterated with a 32-bit counter (initially 1) and the shared secret + key-derivation data, until the desired output length is reached.
5. Document the hash function and the counter wrap-around. The counter is incremented for each block; implementations must handle wrap-around correctly, although in practice it does not occur.
6. Record the per-block length. For SHA-256, the output is 256 bits; for SHA-384, 384 bits; for SHA-512, 512 bits.
7. Use the published test vectors (SEC 1 Appendix and X9.63 annex) for conformance testing.
8. Where X9.63 KDF is used in a protocol that has migrated to SP 800-56A Rev. 3's KDF, document the migration, including the conversion of the shared-info encoding.

## Validation and evidence

Evidence includes:

- the X9.63 version and KDF identifier recorded in the cryptographic policy;
- the hash function and output length recorded;
- shared-info string recorded and tested;
- test vectors from SEC 1 or X9.63 reproduced by the implementation;
- protocol-specific evidence where the KDF is integrated into a higher-level protocol.

## Failure correction

Common defects include:

- Using the X9.63 KDF construction but assuming it is identical to SP 800-56A Rev. 3's KDF. The two constructions differ in shared-info encoding and counter handling.
- Zero-padding the shared secret x-coordinate, which alters the KDF input.
- Using SHA-1 with the X9.63 KDF, which is permitted historically but rarely acceptable in current profiles.
- Confusing the X9.63 KDF with the older ANSI X9.42 KDF (for integer-factorization groups), which has a different counter format.

Corrective actions include re-binding the KDF to the correct construction, removing zero-padding from the shared secret, upgrading the hash function where acceptable, and documenting the boundary with SP 800-56A Rev. 3.

## Limitations

X9.63 does not define:

- integer-factorization group KDF (governed by ANSI X9.42);
- the underlying elliptic curve cryptographic primitive (governed by FIPS 186-5 and SP 800-186);
- post-quantum key agreement.

The publication is an industry standard, not a FIPS standard. FIPS-validated modules typically use SP 800-56A Rev. 3's KDF, not X9.63, when claiming FIPS conformance.

## Operational guidance for migration

Profiles migrating from X9.63 to SP 800-56A Rev. 3 should record, for each relying party, the existing shared-info string format, the hash function used, and the output-key layout. The X9.63 KDF uses an empty or fixed initialization counter (1) and the shared-info is concatenated without a length prefix; SP 800-56A Rev. 3 specifies an auxiliary function `AuxFunction` that includes fixed-field encodings and may produce different canonical bytes for the same logical inputs. Implementations should provide a documented conversion path rather than assuming byte-for-byte equivalence between the two constructions.

Where the same ECDH shared secret is consumed by both legacy and new peers, applications should bind the KDF variant explicitly in the protocol identifier (for example, a tag distinguishing X9.63 KDF from SP 800-56A Rev. 3 KDF) and should not silently fall through to either construction on parse failure.

## Cross-protocol evidence

Where the KDF is used in layered protocols (IKEv2, CMS, TLS 1.2 ECDHE_RSA suites, or financial-services protocols such as ISO 20022), the protocol profile should preserve the shared-info encoding and the per-protocol tag. The IKEv2 profile uses a different shared-info construction from the one used by CMS; the two should not be mixed without re-running the KAT vectors against the integrating protocol's test suite.

## Canonical sources

- ANSI X9.63-2011, *Public Key Cryptography for the Financial Services Industry — Key Agreement and Key Transport Using Elliptic Curve Cryptography* (ANSI X9 store): https://webstore.ansi.org/standards/ascx9/ansix9632011
- SEC 1, *Standards for Efficient Cryptography Group 1: Elliptic Curve Cryptography* (SECG archive): https://www.secg.org/sec1-v2.pdf
- NIST SP 800-56A Rev. 3, *Recommendation for Pair-Wise Key-Establishment Schemes Using Discrete Logarithm Cryptography* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/56/a/r3/final

Sources were verified on September 1, 2026.
