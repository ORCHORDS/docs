# NIST SP 800-90A Rev. 1 DRBG Version Governance

## Purpose

NIST SP 800-90A Revision 1, *Recommendation for Random Number Generation Using Deterministic Random Bit Generators* (June 2015), specifies three approved deterministic random bit generators (DRBGs): Hash_DRBG, HMAC_DRBG, and CTR_DRBG. These are the constructions used to derive cryptographically strong pseudorandom outputs from an entropy source inside FIPS-validated cryptographic modules.

Profiles that claim FIPS-approved random number generation should cite SP 800-90A Rev. 1 explicitly, identify which DRBG is used, and document the entropy source and the seeding mechanism that provides the DRBG's seed material.

## Current context and source status

SP 800-90A Rev. 1 was published in June 2015 and supersedes the original SP 800-90A (January 2012). It removed the Dual_EC_DRBG and corrected the entropy-input and nonce-length rules. A second revision is in draft, but Rev. 1 remains the published version. SP 800-90B (entropy source models) and SP 800-90C (DRBG constructions using approved cryptographic primitives, including post-quantum primitives) are companion documents.

## Governance pattern

1. Cite SP 800-90A Rev. 1 explicitly. Do not cite SP 800-90A without the revision, since Rev. 2 (draft) may restructure the document.
2. Identify the DRBG construction used (Hash_DRBG, HMAC_DRBG, or CTR_DRBG) and the underlying cryptographic primitive (for CTR_DRBG, AES with a 128-bit, 192-bit, or 256-bit key).
3. Record the entropy source and the SP 800-90B conformance evidence. SP 800-90A Rev. 1 assumes a working entropy source; it does not validate the entropy source itself.
4. Document the seeding mechanism. The DRBG requires a seed of at least the security strength in bits and a nonce. Implementations should ensure that the entropy and the nonce are independent and that the entropy estimate meets the requested security strength.
5. Record the security strength (for example 128-bit, 192-bit, or 256-bit) and ensure that the output length does not exceed the DRBG's reseed interval.
6. Implement and document the reseed and prediction-resistance rules. CTR_DRBG with a derivation function can support prediction resistance; without it, an internal state compromise can predict past output.
7. Document the use of personalization strings and additional input. These are mixed into the seed but are not substitutes for entropy.
8. Do not use the deprecated Dual_EC_DRBG. Implementations that previously supported it must remove the construction.

## Validation and evidence

Evidence includes:

- the DRBG identifier (Hash_DRBG, HMAC_DRBG, CTR_DRBG with AES-128/192/256) recorded in the cryptographic module's policy;
- the entropy source's SP 800-90B evidence;
- the seeding process, including entropy-input length and nonce length;
- the reseed interval and prediction-resistance flag;
- test vectors from SP 800-90A reproduced by the implementation;
- documented handling of personalization strings and additional input.

## Failure correction

Common defects include:

- Citing SP 800-90A without identifying the DRBG construction, hiding whether CTR_DRBG, HMAC_DRBG, or Hash_DRBG is used.
- Using the DRBG with a security strength that exceeds the entropy available from the seeding mechanism.
- Forgetting the reseed interval and allowing the DRBG to produce more output than allowed between reseeds.
- Including Dual_EC_DRBG as a selectable DRBG despite its removal in Rev. 1.

Corrective actions include binding the policy to a single DRBG, ensuring entropy > security strength, scheduling reseeds, and removing deprecated constructions.

## Limitations

SP 800-90A Rev. 1 does not define:

- the entropy source (governed by SP 800-90B);
- post-quantum DRBGs (governed by SP 800-90C draft);
- non-deterministic random number generators.

The publication is not itself a FIPS 140 validation; it is the algorithm standard used as input to module validation.

## Entropy-source integration

A FIPS-validated module that runs an SP 800-90A DRBG must combine the DRBG with a SP 800-90B-conformant entropy source. The DRBG's seed must contain at least `security_strength` bits of min-entropy, drawn from the entropy source, and a nonce that is either drawn from a separate entropy source or is a value that cannot reasonably be predicted. Implementations that reuse the same entropy pool for both the seed and the nonce should document that fact and justify why the two contributions remain independent.

## Reseed discipline

Each DRBG variant supports a reseed interval. Implementations must enforce that interval and must generate a fresh seed from the entropy source before producing additional output beyond the interval. CTR_DRBG with a derivation function can be operated in prediction-resistance mode, in which every output request is paired with a fresh seed; this mode is recommended for long-lived keys and for cryptographic operations whose compromise would have material impact.

## Post-quantum context

SP 800-90A Rev. 1 does not include DRBG constructions based on SHA-3 or on lattice primitives; SP 800-90C (draft) is expected to add post-quantum DRBG constructions when finalized. Until SP 800-90C is published, the existing CTR_DRBG and Hash_DRBG remain acceptable, and the underlying primitives (AES-256, SHA-256/384/512) remain FIPS-approved. Quantum risk for DRBGs is dominated by the entropy-source analysis, not by the DRBG construction itself.

## Canonical sources

- NIST SP 800-90A Rev. 1, *Recommendation for Random Number Generation Using Deterministic Random Bit Generators* (NIST CSRC publication page): https://csrc.nist.gov/pubs/sp/800/90/a/r1/final
- NIST SP 800-90B, *Recommendation for the Entropy Sources Used for Random Bit Generation* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/90/b/final
- NIST SP 800-90C (draft), *Recommendation for Random Bit Generator (RBG) Constructions* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/90/c/draft

Sources were verified on September 1, 2026.
