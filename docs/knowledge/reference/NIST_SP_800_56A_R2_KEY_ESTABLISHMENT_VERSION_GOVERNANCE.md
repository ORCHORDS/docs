# NIST SP 800-56A Rev 2 Key Establishment Governance

## Purpose

NIST SP 800-56A Rev 2, *Recommendation for Pair-Wise Key Establishment Schemes Using Discrete Logarithm Cryptography* (August 2015, with amendment), specifies Diffie-Hellman and MQV key establishment schemes over finite fields (DH) and elliptic curves (ECDH/ECMQV), including domain parameter generation/validation, key pair generation, and the shared-secret derivation and key-derivation steps that follow.

Implementations performing DH/ECDH in FIPS scope should cite SP 800-56A Rev 2 explicitly, record the scheme, curve/group, and KDF, and enforce the owner/user key-validation requirements.

## Governance pattern

1. Cite SP 800-56A Rev 2 and record the scheme (DH/ECDH, static or ephemeral) with the domain parameters: NIST curves (P-256/384/521) or approved finite-field groups; X25519/X448 follow RFC 7748 with NIST treatment under SP 800-56A Rev 2's annex provisions for safe-prime groups.
2. Validate domain parameters: generate per the standard or use approved named parameters; unvalidated custom parameters are outside validation.
3. Validate public keys per the scheme's requirements before computing shared secrets; invalid-curve and small-subgroup inputs must be rejected per the standard's public-key validation steps (or handled by a conformant implementation whose ladder inherently addresses them — follow the standard's assurance categories).
4. Apply an approved KDF (SP 800-108, or HKDF where the protocol defines it) to the shared secret; the raw shared secret Z must never be used as a key directly.
5. Distinguish static and ephemeral usage: static-static and ephemeral-static schemes have different assurance properties and validation criteria; record which the protocol uses.
6. For key confirmation, apply the standard's options where the protocol requires explicit confirmation; skip where the derived keys' use provides implicit confirmation, per protocol spec.
7. Manage static key pairs per SP 800-57: usage periods, rotation, and destruction; ephemeral keys are single-use by definition.
8. Validate through ACVP (KAS/KAS-ECC/KAS-FFC components) and reproduce the published test vectors.

## Validation and evidence

Evidence includes:

- scheme, domain parameters, and KDF recorded per service;
- parameter validation provenance (named vs generated);
- public-key validation approach traced to the standard's categories;
- static key lifecycle records per SP 800-57;
- ACVP KAS validation results;
- protocol's key-confirmation decision documented.

## Failure correction

Common defects include:

- Raw shared secret used as a key without a KDF.
- Public-key validation skipped where the standard requires it, enabling invalid-curve attacks.
- Static keys past their usage period or shared across protocols without separation.
- Custom domain parameters used without the standard's generation/validation.

Corrective actions include KDF insertion, validation conformance, key rotation, and named-parameter adoption.

## Limitations

SP 800-56A Rev 2 governs classical discrete-log schemes; post-quantum key establishment (ML-KEM, FIPS 203) is separate. The recommendation's scheme profiles interlock with protocol specifications (TLS, IKE) that make their own selections; conformance is joint.

## Shared-secret hygiene

The shared secret Z is an intermediate value: uniform enough for key derivation, not a key. Every deployed failure class around Z — using it directly, logging it, deriving multiple keys without context separation — is prevented by the same discipline: Z feeds exactly one KDF invocation with protocol-defined context, is never persisted, and never appears in logs. Protocol context strings in the KDF carry the separation burden; treat them as part of the protocol's interface.

## Canonical sources

- NIST SP 800-56A Rev 2, *Recommendation for Pair-Wise Key Establishment Schemes Using Discrete Logarithm Cryptography* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/56a/r2/final
- NIST SP 800-56B Rev 2, *Recommendation for Pair-Wise Key Establishment Using Integer Factorization Cryptography* (RSA counterpart): https://csrc.nist.gov/pubs/sp/800/56b/r2/final
- NIST SP 800-56C Rev 2, *Recommendation for Key-Derivation Methods in Key Establishment Schemes*: https://csrc.nist.gov/pubs/sp/800/56c/r2/final
- RFC 7748, *Elliptic Curves for Security* (RFC Editor): https://www.rfc-editor.org/rfc/rfc7748
- NIST SP 800-57 Part 1 Rev 5, *Key Management Guidance* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/57/part1/r5/final

Sources were verified on September 2, 2026.
