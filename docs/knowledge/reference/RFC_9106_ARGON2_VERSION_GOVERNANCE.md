# RFC 9106 Argon2 Version Governance

## Purpose

RFC 9106, *Argon2 Memory-Hard Function for Password Hashing and Proof-of-Work Applications* (September 2019), specifies the Argon2 family of memory-hard functions: Argon2d, Argon2i, and Argon2id. Argon2 won the Password Hashing Competition (2013-2015) and is the recommended default for password storage where a memory-hard KDF is required.

Implementations that hash passwords with Argon2 should cite RFC 9106 explicitly, record the variant and cost parameters (memory, iterations, parallelism), and select the variant deliberately for the threat model rather than by default.

## Current context and source status

RFC 9106 was published in September 2019 as an Informational RFC and is not updated or obsoleted. RFC 9106 remains the governing specification; subsequent IETF work on password storage guidance is tracked through the CFRG. The reference C implementation and the Argon2 test vectors are maintained alongside the specification; the Internet-Draft successor work continues to track errata.

## Governance pattern

1. Cite RFC 9106 explicitly and identify the variant: Argon2id combines side-channel resistance (data-independent addressing of Argon2i) with GPU-resistance (data-dependent addressing of Argon2d) and is the default for password storage.
2. Record the cost parameters: memory exponent (m), iterations (t), parallelism (p), and output length. These are security parameters; changes are cryptographic changes, not tuning.
3. Generate a fresh 16-byte salt per password record with a cryptographic random generator; salt reuse across records defeats the memory-hard cost model at scale.
4. Record the version number (0x13) and encode parameters with the hash in the standard PHC string format (`$argon2id$v=19$m=...,t=...,p=...$salt$hash`) so verification is self-describing.
5. Do not substitute Argon2d for Argon2id in server-side password storage: Argon2d's data-dependent addressing is tuned for proof-of-work and is more exposed to side-channel attacks in interactive contexts.
6. Do not use Argon2 for high-entropy input; HKDF (RFC 5869) or the NIST SP 800-108 KDFs are the appropriate constructions when the input is already a uniform key.
7. Calibrate parameters against the deployment server's memory budget and target verification latency (typically 50-500 ms), and re-calibrate on hardware refresh; record the calibration rationale.
8. Reproduce the RFC 9106 test vectors (Appendix) before production use, including the tagged and untagged variants.

## Validation and evidence

Evidence includes:

- Argon2 variant, version, and cost parameters recorded in the cryptographic module's policy;
- PHC string format records for stored hashes with embedded parameters;
- salt generation policy and evidence of per-record uniqueness;
- calibration record tying parameters to target latency and hardware budget;
- RFC 9106 Appendix test vectors reproduced by the implementation;
- variant selection rationale (Argon2id default) documented.

## Failure correction

Common defects include:

- Cost parameters left at library defaults that are below the deployment's target security (for example m=32 MB in a library default when the budget allows gigabytes).
- Salt reuse across records, collapsing per-record independence.
- Argon2d selected for password storage, exposing data-dependent addressing to cache-timing observation.
- Parameters omitted from the stored record, making future re-verification and migration impossible.

Corrective actions include recalibration, per-record salt regeneration with forced rehash at next login, variant migration to Argon2id, and parameter embedding in PHC format.

## Limitations

RFC 9106 does not define:

- application password policy; Argon2 hardens the hash, not the password's entropy;
- post-quantum claims; memory-hardness targets classical GPU/ASIC attackers, and password entropy remains the binding constraint;
- key derivation from high-entropy input; that is HKDF's scope.

Argon2 is a password-hashing and proof-of-work function, not a general-purpose KDF, a cipher, or a MAC.

## Parameter calibration discipline

Argon2's security is parameterized: memory cost dominates ASIC/GPU resistance, iteration count multiplies time cost, parallelism trades lane count against memory bandwidth utilization. A calibration is invalid when hardware changes; recalibrate on server generation refresh and record the target verification latency. The RFC's encoded-parameter format exists so migrations are data-driven: read old parameters, verify, rehash under new parameters at next authentication, and write the upgraded record.

## Canonical sources

- RFC 9106, *Argon2 Memory-Hard Function for Password Hashing and Proof-of-Work Applications* (RFC Editor): https://www.rfc-editor.org/rfc/rfc9106
- NIST SP 800-63B, *Digital Identity Guidelines — Authentication and Lifecycle Management* (password hashing guidance): https://pages.nist.gov/800-63-3/sp800-63b.html
- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html

Sources were verified on September 2, 2026.
