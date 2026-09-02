# FIPS 186-5 Digital Signature Standard Version Governance

## Purpose

FIPS 186-5, *Digital Signature Standard (DSS)* (February 2023), approves three digital signature techniques: ECDSA, EdDSA, and RSA (RSASSA-PKCS1-v1_5 and RSASSA-PSS). It removes DSA as an approved signature generation technique and aligns hash usage with FIPS 180-4 and SP 800-208.

Implementations producing or verifying signatures under FIPS validation should cite FIPS 186-5 explicitly, record the approved technique and parameter set, and observe the standard's generation and verification conditions.

## Current context and source status

FIPS 186-5 was published February 3, 2023, superseding FIPS 186-4. DSA is retained only for legacy verification; new signature generation with DSA is not approved. FIPS 186-5 references NIST SP 800-208 (deterministic ECDSA and EdDSA recommendations). The FIPS 186-5 Implementer's Guide provides A-to-Z implementation detail. CAVP/ACVPP validation under FIPS 186-5 proceeds through the Cryptographic Algorithm Validation Program.

## Governance pattern

1. Cite FIPS 186-5 and record the technique: ECDSA (with the curve), EdDSA (Ed25519/Ed448), or RSA (RSASSA-PKCS1-v1_5 or RSASSA-PSS with the modulus size and hash).
2. Select from approved curves for ECDSA: the NIST curves P-192 through P-521 per the standard's tables; non-approved curves are outside FIPS validation.
3. Use deterministic ECDSA construction per SP 800-208 where side-channel resilience is required; randomized ECDSA per FIPS 186-5 requires high-quality per-signature randomness.
4. For RSA, prefer RSASSA-PSS for new deployments; RSASSA-PKCS1-v1_5 remains approved with constraints — record the choice and rationale.
5. Pair each technique only with approved hash functions per FIPS 180-4/SP 800-208 constraints; a technique-hash pairing outside the standard's tables is a validation failure.
6. Maintain key lifecycle per SP 800-57: generation in validated modules, usage periods, and destruction; FIPS 186-5 signatures are only as compliant as the module producing them.
7. Verify DSA legacy signatures only where required for interoperability; new DSA generation is prohibited in FIPS contexts.
8. Reproduce the A-to-Z test vectors from the Implementer's Guide and validate through ACVP for the technique and parameter set.

## Validation and evidence

Evidence includes:

- technique, curve/modulus, and hash recorded per signing service in the module policy;
- deterministic vs randomized ECDSA decision with SP 800-208 citation where deterministic;
- RSA variant selection rationale (PSS preferred);
- module validation certificate covering the technique and parameters;
- ACVP test results for the parameter set;
- key lifecycle records per SP 800-57.

## Failure correction

Common defects include:

- Randomized ECDSA with a weak or repeating nonce, exposing the private key through lattice attacks on repeated nonces.
- Technique-hash pairing outside FIPS 186-5's approved tables.
- DSA generation retained in a FIPS-bound service after migration deadlines.
- RSASSA-PKCS1-v1_5 selected without a recorded rationale where PSS was available.

Corrective actions include migration to deterministic ECDSA or EdDSA, alignment of hash pairings, DSA generation removal, and PSS adoption with re-validation.

## Limitations

FIPS 186-5 does not define:

- certificate formats or PKI; that is X.509/RFC 5280's scope;
- post-quantum signatures; ML-DSA and companions are specified in FIPS 204 and separate standards, not 186-5;
- protocols; it defines signature techniques only.

FIPS 186-5 governs FIPS-validated contexts; other regimes (CNSA, EU, national profiles) impose different suite constraints.

## Deterministic versus randomized ECDSA

RFC 6979-style deterministic ECDSA (as recommended by SP 800-208) eliminates the per-signature nonce, removing the most catastrophic ECDSA failure mode — private key recovery from biased nonces — at no security cost. FIPS 186-5 approves deterministic ECDSA and EdDSA constructions; new FIPS-bound deployments should default to deterministic constructions unless a concrete reason requires randomness.

## Canonical sources

- FIPS 186-5, *Digital Signature Standard* (NIST CSRC, February 2023): https://csrc.nist.gov/pubs/fips/186-5/final
- NIST SP 800-208, *Recommendation for Stateful Hash-Based Signature Schemes / deterministic ECDSA and EdDSA*: https://csrc.nist.gov/pubs/sp/800/208/final
- FIPS 180-4, *Secure Hash Standard*: https://csrc.nist.gov/pubs/fips/180-4/upd1/final
- NIST — CAVP/ACVP Digital Signature validation: https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program
- NIST SP 800-57 Part 1 Rev 5, *Key Management Guidance*: https://csrc.nist.gov/pubs/sp/800/57/part1/r5/final

Sources were verified on September 2, 2026.
