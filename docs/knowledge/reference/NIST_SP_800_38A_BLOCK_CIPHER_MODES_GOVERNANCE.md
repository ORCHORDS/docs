# NIST SP 800-38A Block Cipher Modes Governance

## Purpose

NIST SP 800-38A specifies five confidentiality modes of operation for symmetric block ciphers: ECB, CBC, CFB, OFB, and CTR. Governance ensures that cryptographic applications use appropriate modes for confidentiality, avoid insecure modes (ECB), and apply authenticated encryption where integrity is also required.

## Current context and source status

NIST SP 800-38A was published in 2001. The standard remains current for the five specified modes, though ECB is not recommended for general use. Authenticated encryption modes (CCM, GCM) are addressed in companion publications (SP 800-38C, SP 800-38D). Verify the current NIST guidance before treating any specific mode as the only choice for a given application.

## Governance workflow and controls

### 1. Avoid ECB

Do not use ECB mode for confidentiality. ECB encrypts each block independently and leaks patterns.

### 2. Apply CBC with care

If CBC is used, apply an authenticated encryption scheme (e.g., encrypt-then-MAC with HMAC). Verify integrity before decrypting. Manage IV unpredictability. Manage padding (PKCS#7) and padding oracle attacks.

### 3. Prefer CTR

CTR mode turns a block cipher into a stream cipher. Apply with unique nonces per message. Use authenticated encryption (GCM or CCM) where integrity is required.

### 4. Apply authenticated encryption

Apply authenticated encryption (AES-GCM, AES-CCM, ChaCha20-Poly1305) for most use cases. Authenticated encryption provides both confidentiality and integrity.

### 5. Manage IVs and nonces

Manage IVs and nonces per the mode requirements:

- CBC IVs: unpredictable per message;
- CTR nonces: unique per message;
- GCM nonces: unique per encryption key.

Document the management approach.

### 6. Apply key rotation

Apply key rotation per the documented key management policy. Use key derivation functions (KBKDF, SP 800-108) to derive per-message keys.

### 7. Document the choice

Document the mode selection and rationale per application. Include the algorithm, mode, key size, IV/nonce size, and source of the implementation.

## Validation and evidence

- Cryptographic configuration register.
- Mode selection rationale.
- IV/nonce management procedure.
- Authenticated encryption usage evidence.

## Failure correction

Common defects include use of ECB, missing authentication, and nonce reuse. Corrective actions include a code review check for ECB, a configuration review for authenticated encryption, and a nonce uniqueness verification test.

## Limitations

- SP 800-38A is specific to confidentiality modes; integrity requires additional mechanisms.
- Block cipher modes do not protect against all attacks (e.g., padding oracle, replay).
- Authenticated encryption modes have additional requirements (e.g., tag length, AAD).
- Implementation must follow standards closely; deviation can introduce vulnerabilities.

## Canonical sources

- NIST SP 800-38A, Recommendation for Block Cipher Modes of Operation — Methods and Techniques, 2001.
- NIST SP 800-38C, Recommendation for Block Cipher Modes of Operation: The CCM Mode for Authentication and Confidentiality, 2004.
- NIST SP 800-38D, Recommendation for Block Cipher Modes of Operation: Galois/Counter Mode (GCM) and GMAC, 2007.
- NIST SP 800-38F, Recommendation for Block Cipher Modes of Operation: Key Wrapping, current edition.

## Scope note

This article belongs to the reference leaf and cross-references the security leaf for cryptographic controls, the engineering leaf for cryptographic implementation, and the platforms leaf for cryptographic modules.
