# ANSI X9.42:2021 Key Agreement Using DH Governance

## Purpose

ANSI X9.42:2021, "Public Key Cryptography for the Financial Services Industry — Agreement of Symmetric Keys Using Discrete Logarithm Cryptography," specifies Diffie-Hellman (DH) key agreement and elliptic curve Diffie-Hellman (ECDH) key agreement for financial services. The standard covers domain parameter generation, key generation, key agreement, key confirmation, and the use of derived symmetric keys. This article governs the application of ANSI X9.42 so key agreement in financial services uses the algorithms, parameters, and validation steps the standard requires.

## Scope

The standard applies to financial services organizations that use DH or ECDH key agreement. Within this knowledge base, the article covers the DH and ECDH algorithms, the domain parameters, the validation of the parameters, the key agreement flow, and the documentation of the key agreement. It does not cover other key agreement schemes (e.g., RSA-based key transport); readers should consult other ANSI X9 parts for those.

## Workflow

1. Establish the key agreement policy: scope, algorithms (DH, ECDH), parameters, and the relationship to the symmetric scheme of ANSI X9.24.
2. Select or generate the domain parameters:
   - For DH: select a safe prime, generator, and validate them.
   - For ECDH: select a named curve (NIST P-256, P-384, brainpool curves) appropriate to the security and regulatory requirements.
3. Generate key pairs using validated hardware. Validate the public key before use (e.g., reject weak or non-contributing keys).
4. Execute the key agreement:
   - Each party generates an ephemeral key pair (or uses a static key pair, per policy).
   - Both parties exchange public keys.
   - Both parties compute the shared secret Z = (Y other)^X local.
   - Apply a key derivation function (KDF) to derive the symmetric session key from Z.
5. Perform key confirmation: both parties confirm they have derived the same key.
6. Document the agreed parameters, the key agreement flow, the derived key, and the use of the key.

## Controls and evidence

Key agreement controls include the documented parameters, the validated key pairs, the key agreement records, the KDF specification, and the key confirmation evidence. Each key agreement operation should be traceable from the parameters through the agreement to the derived key.

## Validation

Validation should confirm the parameters are validated, the public keys are validated, the KDF is applied correctly, the key confirmation passes, and the agreed key is used only for the intended purpose. FIPS 140-3 validation of the underlying cryptographic module confirms the implementation.

## Failure correction

Common failure modes: weak parameters are accepted (correct: validate parameters against the standard's requirements); the KDF is not applied (correct: apply a standardized KDF such as NIST SP 800-56A); key confirmation is skipped (correct: confirm key agreement between parties); the same key is used for multiple purposes (correct: derive distinct keys per purpose from the shared secret); validation of the other party's public key is skipped (correct: validate each public key before computing Z).

## Limitations

ANSI X9.42 specifies DH/ECDH; it does not prescribe a single algorithm or parameter set. The standard does not certify any implementation. Key agreement does not authenticate the parties by itself; the standard addresses authentication through key confirmation and through the use of authenticated key exchange (AKE) protocols.

## Scope note

This article summarizes project-neutral reference use of ANSI X9.42:2021. It does not assert any specific implementation's conformance or claim any certification outcome.

## Canonical sources

- ANSI X9.42:2021 — Public Key Cryptography for the Financial Services Industry — Agreement of Symmetric Keys Using Discrete Logarithm Cryptography: https://webstore.ansi.org/standards/ascx9/ansix9422021
- NIST SP 800-56A — Recommendation for Pair-Wise Key-Establishment Using Integer Factorization Cryptography: https://csrc.nist.gov/publications/detail/sp/800-56a/rev-3/final