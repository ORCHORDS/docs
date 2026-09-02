# RFC 8018 PBKDF2 Version Governance

## Purpose

RFC 8018, *PKCS #5: Password-Based Cryptography Specification Version 2.1* (January 2017), specifies PBKDF2, the dominant password-based key derivation function in existing protocols and storage formats, along with the PBES1/PBES2 encryption schemes.

Implementations using PBKDF2 should cite RFC 8018 explicitly, record the PRF (typically HMAC-SHA-256), the iteration count, and salt handling, and understand where PBKDF2 is the legacy-compatible choice versus where Argon2id is the better default.

## Current context and source status

RFC 8018 was published January 2017 (obsoleting RFC 2898) and is not further updated. PBKDF2 remains approved in FIPS contexts (SP 800-132 governs NIST's PBKDF2 profile) and embedded in many formats (encrypted archives, key stores, disk encryption). OWASP and NIST SP 800-63B guidance point new password-storage deployments toward memory-hard alternatives (Argon2id) where memory cost can be enforced; PBKDF2 persists where format or validation constraints require it.

## Governance pattern

1. Cite RFC 8018 and record the parameters: PRF, iteration count (c), salt length, and output key length; all four are security parameters.
2. Use HMAC with SHA-256 or SHA-512 as the PRF; HMAC-SHA-1 remains interoperable in legacy formats but is closed for new designs.
3. Enforce iteration counts from current guidance (OWASP's calibration tables for PBKDF2-HMAC-SHA-256 are in the millions), calibrated to target verification latency; library defaults from a decade ago are not acceptable.
4. Generate per-record random salts of at least 64 bits (128 recommended); salt reuse defeats the iteration cost against precomputation.
5. Use PBES2 (PBKDF2 + AES) for password-based encryption in new designs following the RFC; PBES1 is legacy.
6. Where the deployment can enforce server memory cost, prefer Argon2id (RFC 9106) for new password storage; record the decision and the constraint driving PBKDF2 where it is retained (format compatibility, FIPS module scope).
7. Apply PBKDF2 only to password input; for high-entropy input use HKDF (RFC 5869) or SP 800-108 KDFs.
8. Reproduce the RFC 8018 Appendix B test vectors for the chosen PRF and iteration count.

## Validation and evidence

Evidence includes:

- PRF, iteration count, salt length, and output length recorded per service;
- calibration record tying iteration count to target latency on deployment hardware;
- salt generation policy with per-record uniqueness evidence;
- migration decision record (Argon2id default vs PBKDF2 retention rationale);
- RFC 8018 Appendix B test vectors reproduced;
- module validation scope covering the PRF and PBES2 mode where FIPS-bound.

## Failure correction

Common defects include:

- Iteration counts left at format minimums or library defaults (1,000 in the RFC's examples) instead of calibrated millions.
- Salt reuse or fixed salts, enabling precomputation across records.
- PBKDF2 applied to high-entropy input where HKDF is correct.
- HMAC-SHA-1 PRF retained in new designs.

Corrective actions include recalibration with stored-parameter migration (verify with old parameters, rehash with new), per-record salt regeneration at next authentication, and PRF migration where format compatibility allows.

## Limitations

RFC 8018 does not define:

- memory-hardness; PBKDF2 is CPU-hard only, and GPU/ASIC attackers gain proportional advantage — the reason Argon2id is preferred where enforceable;
- password policy or entropy requirements;
- authenticated encryption; PBES2 composes a KDF with a cipher, and authentication is layered separately.

PBKDF2 is a password-based KDF, not a general KDF or a hash.

## Iteration calibration discipline

PBKDF2's security scales linearly with iteration count, so calibration is the entire game: choose the count that puts verification in the target latency band (commonly 100-500 ms) on the deployment hardware, and re-calibrate on hardware refresh. Stored records must embed the parameters (the RFC's AlgorithmIdentifier and PBKDF2-params carry them) so migration is verifiable — a PBKDF2 record without embedded parameters is unverifiable and un-migratable.

## Canonical sources

- RFC 8018, *PKCS #5: Password-Based Cryptography Specification Version 2.1* (RFC Editor): https://www.rfc-editor.org/rfc/rfc8018
- NIST SP 800-132, *Recommendation for Password-Based Key Derivation* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/132/final
- RFC 9106, *Argon2 Memory-Hard Function* (RFC Editor, successor default): https://www.rfc-editor.org/rfc/rfc9106
- NIST SP 800-63B, *Digital Identity Guidelines — Authentication and Lifecycle Management*: https://pages.nist.gov/800-63-3/sp800-63b.html
- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html

Sources were verified on September 2, 2026.
