# NIST SP 800-185 SHA-3 Derived Functions Version Governance

## Purpose

NIST SP 800-185, *SHA-3 Derived Functions: cSHAKE, KMAC, TupleHash, and ParallelHash* (December 2016), specifies four SHA-3-based primitives built on top of FIPS 202's SHA-3 and SHAKE functions. cSHAKE is a customizable variant of SHAKE; KMAC is a keyed-hash message authentication code based on Keccak; TupleHash is a variable-length hash for tuples of strings; and ParallelHash is a variable-length hash for very long messages that can be processed in parallel.

Profiles that adopt SHA-3 derived functions should cite SP 800-185 explicitly, identify which derived function is in scope, and bind the function choice to the underlying FIPS 202 SHA-3 primitive.

## Current context and source status

SP 800-185 was finalized on December 22, 2016. A planning note dated March 13, 2025 indicates that NIST has decided to revise this publication. No published revision exists yet. Until a new revision is published, the December 2016 publication remains the current NIST specification for these primitives.

## Governance pattern

1. Cite SP 800-185 plus the underlying FIPS 202 (SHA-3 Standard) and the relevant SP 800-107 (Cryptographic Hash Algorithm guidance) or companion publications when documenting the cryptographic suite.
2. Identify which derived function is in scope (cSHAKE, KMAC, TupleHash, ParallelHash) and the customization string `N` and the name string `S` for cSHAKE/KMAC applications. The customization string is a critical input; its omission is a frequent defect.
3. Record the output length L (in bits) and the security strength. KMAC and the SHA-3 family provide a tunable output length up to the SHA-3 security strength.
4. For KMAC, choose between KMAC128 and KMAC256 per the application's security strength requirements. Mixing the two without documenting the boundary can introduce inconsistencies.
5. For cSHAKE, distinguish between SHAKE128 and SHAKE256 and bind the choice to the output length. cSHAKE reverts to SHAKE when both customization string and name string are empty.
6. For ParallelHash, document the block size B and the configuration of the parallel-tree structure; mis-sized blocks can affect performance but not security.
7. For TupleHash, document the tuple separator and any application-specific encoding. TupleHash is designed for ordered lists of strings and is not a generic serializer.
8. Test against the published test vectors (SP 800-185 Appendix) for each function and against FIPS 202 test vectors for the underlying SHAKE and SHA-3 functions.

## Validation and evidence

Evidence includes:

- the SHA-3 derived function identifier (cSHAKE128, cSHAKE256, KMAC128, KMAC256, TupleHash128, TupleHash256, ParallelHash128, ParallelHash256) recorded in the cryptographic policy;
- customization string and name string recorded and tested;
- output length and security strength recorded;
- FIPS 202 conformance evidence for the underlying SHA-3 primitive;
- test vectors from SP 800-185 reproduced by the implementation;
- parallel-tree structure and block size recorded for ParallelHash.

## Failure correction

Common defects include:

- Calling the function "SHAKE" or "SHA-3" without identifying cSHAKE, KMAC, TupleHash, or ParallelHash, hiding the construction.
- Omitting the customization string when cSHAKE is required, falling back to SHAKE without context separation.
- Using KMAC without selecting between KMAC128 and KMAC256, leaving the security strength ambiguous.
- Treating TupleHash as a generic serializer, when it is a fixed-construction hash for ordered tuples.

Corrective actions include re-binding the customization string, choosing the KMAC variant explicitly, and re-running the SP 800-185 test vectors against the corrected function.

## Limitations

SP 800-185 does not define:

- the underlying SHA-3 primitive (governed by FIPS 202);
- key management (governed by SP 800-57 Part 1 Rev. 5);
- a confidentiality mechanism; KMAC is a MAC and does not encrypt;
- a digital signature scheme.

The publication also does not address post-quantum migration; SHA-3 is generally considered quantum-resistant at the configured security strength.

## Operational considerations and migration

SP 800-185 is commonly adopted alongside SP 800-57 Part 1 Rev. 5 for symmetric-key lifecycle management and alongside SP 800-131A Rev. 2 for algorithm assurance labels. The cSHAKE, KMAC, TupleHash, and ParallelHash functions are explicitly approved for use in FIPS-validated modules when paired with FIPS 202 SHA-3 primitives. Implementations should ensure that the module's security policy lists the derived function identifier (for example `KMAC128` or `KMAC256`) rather than a generic `SHA-3` reference, because the derived functions have separate CAVP test coverage.

When migrating from SHA-2-based HMAC constructions (RFC 2104 / FIPS 198-1) to SHA-3-based KMAC, the application must re-derive any per-purpose keys, because the two MAC constructions have different domain-separation requirements and different block-size behavior. A protocol that uses HMAC-SHA-256 in one context and KMAC128 in another should bind the MAC choice to the protocol identifier and should not silently substitute one for the other during signature verification.

## Cross-reference to other NIST publications

- SP 800-107 Rev. 1 provides general guidance on hash algorithm usage and remains relevant for SHA-3 deployments even though it pre-dates SP 800-185's publication.
- SP 800-208, *Recommendation for Stateful Hash-Based Signature Schemes*, uses the SHA-3 family but defines its own construction; do not substitute SP 800-185 primitives for SP 800-208's tree structures.
- NIST's hash-based signature schemes (XMSS, LMS, SPHINCS+) reference the underlying SHA-2 or SHA-3 primitive directly and have their own KAT vectors; mixing them with KMAC or cSHAKE in a single signature path is incorrect.

## Canonical sources

- NIST SP 800-185, *SHA-3 Derived Functions: cSHAKE, KMAC, TupleHash, and ParallelHash* (NIST CSRC publication page): https://csrc.nist.gov/pubs/sp/800/185/final
- NIST SP 800-185 DOI (NIST Computer Security Resource Center): https://doi.org/10.6028/NIST.SP.800-185
- FIPS 202, *SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions* (NIST CSRC): https://csrc.nist.gov/pubs/fips/202/final

Sources were verified on September 1, 2026.
