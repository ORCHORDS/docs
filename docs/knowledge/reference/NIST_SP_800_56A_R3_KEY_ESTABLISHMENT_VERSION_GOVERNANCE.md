# NIST SP 800-56A Rev. 3 Pair-wise Key Establishment Version Governance

## Purpose

NIST Special Publication 800-56A Revision 3 is the current FIPS-140-validated specification for pair-wise key-establishment schemes using discrete-logarithm cryptography. Implementations that advertise key agreement should cite SP 800-56A Rev. 3 explicitly, distinguish finite-field DH, elliptic-curve DH (ECDH), and the cofactor variants (cofactor, full, and "MQV") they permit, and separate key-agreement primitives from key-derivation, transport, or storage choices.

The publication governs a tightly-coupled set of primitives: domain parameters, key-pair generation, shared-secret construction, and the key-derivation function. A claim of compliance that names only a primitive (for example "ECDH") without identifying the agreed scheme, curve class, derivation, and ordering of operations is not the same as a claim of SP 800-56A Rev. 3 compliance.

## Current context and source status

NIST SP 800-56A Rev. 3 was published in April 2018 as the third revision; it superseded Rev. 2 from June 2013 (which itself superseded the original 2007 publication). Rev. 3 adds the One-Pass Unified Model C(1e, 2s, ECC CDH), extends MQV guidance, and clarifies the assumptions under which each scheme provides security.

A planning note dated January 6, 2026 indicates that NIST has decided to update the publication. Until a new revision is finalized, Rev. 3 remains the published version. CMVP validations continue to reference Rev. 3 in module certificates and security policies.

## Governance pattern

1. Cite SP 800-56A Rev. 3 explicitly in design documents, test plans, and conformance evidence. Do not collapse this citation to "SP 800-56A" or "NIST DH" without a revision.
2. Record the specific scheme(s) implemented: dhHybrid1, dhEphem, dhStatic, (Cofactor) ECDH, Full Unified Model C(2e, 2s, ECC CDH), One-Pass Unified Model C(1e, 2s, ECC CDH), or (Cofactor) ECC MQV. Each scheme has different assumptions about initiator and responder contributions and different exposure to key-compromise impersonation.
3. Document domain parameter generation (for finite fields) or curve selection (for ECDH/ECMQV) and verify that the selected curve is on the FIPS-approved list in FIPS 186-5 or a documented allowance in SP 800-186.
4. Pin the key-derivation function. Rev. 3 specifies the concatenation-based KDF (NIST SP 800-108 for password-based scenarios) with concrete construction guidance; substituting a generic HKDF invocation without specifying the auxiliary data, salt, and encoding is not equivalent.
5. Identify whether implementations enforce the SP 800-56A Rev. 3 ordering of operations, including Z calculation before key derivation and explicit handling of the empty-shared-secret case.
6. Treat legacy SP 800-56A Rev. 1/Rev. 2 implementations as a separate, versioned configuration. Coexistence requires explicit per-message or per-session identifier binding.
7. For ECDH/ECMQV, document cofactor handling, validation of static public keys, and whether partial or full public-key validation is performed, because the omission of public-key validation is a known vulnerability class.
8. Record the assurance case: scheme name, curve class, key sizes, derivation, validation, ordering, and rejection of degenerate outputs.

## Validation and evidence

Module validators and conformance testers should expect:

- SP 800-56A Rev. 3 cited in the cryptographic module's security policy and Known Answer Tests.
- domain parameter sets traceable to CAVP (NIST CAVS) test vectors;
- scheme-level test coverage distinguishing ephemeral, static, and unified-model patterns;
- rejection of empty and known-invalid points;
- deterministic ordering and bitwise comparison steps documented in the build evidence.

Successful transport-layer negotiation of a key-establishment suite does not by itself demonstrate SP 800-56A Rev. 3 compliance. Compliance requires the underlying primitive, derivation, and validation to match the specification.

## Failure correction

Implementations most often need to be corrected for:

- Using SP 800-56A Rev. 3 only as a label while computing "ECDH" with HKDF as a placeholder for the specified KDF.
- Failing to validate the static public key before the shared-secret computation, which allows invalid-curve or small-subgroup attacks.
- Adopting a scheme (for example dhEphem) where one party is expected to be ephemeral but a deployment reuses a static key, breaking the scheme's security assumptions.
- Treating the legacy FFC DH small-subgroup set as benign because the protocol layer checks identity rather than key freshness.

The corrective procedure in each case is to re-baseline the implementation against the Rev. 3 specification text, update the KAT vectors, reissue the security policy revision, and re-run CAVS validation.

## Limitations

SP 800-56A Rev. 3 does not specify:

- Password-authenticated key agreement (governed by SP 800-56B family for integer-factorization variants or by SP 800-63 series for human-facing authentication).
- Multi-party or group key agreement beyond two-party schemes.
- Key transport by encryption (governed by SP 800-56B).
- Lattice-based post-quantum primitives.

A claim of "SP 800-56A Rev. 3 quantum-safe" is not supported by the publication.

## Canonical sources

- NIST SP 800-56A Rev. 3, *Recommendation for Pair-Wise Key-Establishment Schemes Using Discrete Logarithm Cryptography* (NIST CSRC publication page): https://csrc.nist.gov/pubs/sp/800/56/a/r3/final
- NIST SP 800-56A Rev. 3 PDF (NIST Computer Security Resource Center): https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-56Ar3.pdf
- NIST SP 800-186, *Recommendations for Discrete Logarithm-based Cryptography: Elliptic Curve Domain Parameters*: https://csrc.nist.gov/pubs/sp/800/186/final

Sources were verified on September 1, 2026.
