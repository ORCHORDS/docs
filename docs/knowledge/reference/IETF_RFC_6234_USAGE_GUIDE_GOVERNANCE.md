# IETF RFC 6234 SHA-256 Usage Governance

## Purpose

IETF RFC 6234 specifies the secure hash algorithms SHA-256, SHA-384, and SHA-512. Governance ensures that cryptographic applications use these hash functions correctly, that truncated SHA-256 outputs are not used for security-critical applications, and that collisions do not affect application security.

## Current context and source status

RFC 6234 was published in 2011, updating RFC 4634. The RFC specifies the three SHA-2 variants and provides test vectors and implementation guidance. NIST FIPS 180-4 also specifies the SHA-2 family. Verify the current IETF and NIST publications before treating any specific hash output length as the only appropriate choice.

## Governance workflow and controls

### 1. Use SHA-256 or longer

Use SHA-256 or longer output. SHA-1 should not be used for new applications; MD5 and other legacy hashes should not be used.

### 2. Apply per-application requirements

Apply per-application requirements:

- digital signatures: SHA-256 or stronger;
- message authentication codes: HMAC-SHA-256 or stronger;
- key derivation: HKDF or PBKDF2 with SHA-256;
- password hashing: Argon2id, scrypt, or PBKDF2 with high iteration count.

Document the choice and rationale per application.

### 3. Manage truncation

Manage truncation carefully. Truncated SHA-256 outputs may be acceptable for specific applications (e.g., key fingerprinting) but should not be used for security-critical applications.

### 4. Address collision resistance

Use SHA-256 or stronger to maintain collision resistance. Apply domain separation where collisions across uses could affect security.

### 5. Apply deterministic construction

Use SHA-256 deterministically. Avoid using the same hash output for multiple security-critical purposes.

### 6. Document implementation

Document the hash function, the parameters, and the library used. Verify the implementation against test vectors.

### 7. Plan migration to SHA-3

Plan migration to SHA-3 (FIPS 202) where required. SHA-3 offers a different construction (Keccak) and may be preferred for new applications.

## Validation and evidence

- Hash function inventory.
- Implementation verification against test vectors.
- Migration plan to SHA-3 (if applicable).

## Failure correction

Common defects include use of MD5 or SHA-1, truncated outputs for security-critical applications, and missing test vector verification. Corrective actions include a hash usage audit, a truncation review, and a test vector verification procedure.

## Limitations

- SHA-256 is collision-resistant but does not provide authentication on its own.
- Truncation reduces security; balance with application requirements.
- SHA-2 is well-analyzed; SHA-3 offers a different security argument.
- Hash function security does not address side-channel attacks.

## Canonical sources

- IETF RFC 6234, US Secure Hash Algorithms (SHA and SHA-based HMAC and HKDF), 2011.
- NIST FIPS 180-4, Secure Hash Standard (SHS), current edition.
- NIST FIPS 202, SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions, current edition.

## Scope note

This article belongs to the reference leaf and cross-references the security leaf for cryptographic controls, the engineering leaf for cryptographic implementation, and the standards leaf for cryptographic standards.
