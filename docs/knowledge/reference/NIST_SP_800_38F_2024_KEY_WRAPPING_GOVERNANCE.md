# NIST SP 800-38F:2024 Key Wrapping Governance

## Purpose

NIST SP 800-38F, "Recommendation for Block Cipher Modes of Operation: Methods for Key Wrapping," specifies key wrapping methods based on AES. Key wrapping is the operation of encrypting (and authenticating) cryptographic keys, typically used to protect keys during storage or transport. The publication defines the AES Key Wrap (KW) and AES Key Wrap with Padding (KWP) modes, and addresses use cases including protecting keys at rest, in transit, and in key translation. This article governs the application of SP 800-38F so key wrapping uses the approved methods and parameters.

## Scope

The publication applies to any organization using key wrapping for key protection. Within this knowledge base, the article covers the AES KW and KWP modes, the input/output formats, the use cases, the validation of implementations, and the documentation of key wrapping. It does not cover other key protection techniques (key encryption with asymmetric keys per SP 800-56B); readers should consult that publication separately.

## Workflow

1. Establish the key wrapping policy: scope, use cases (storage, transport, translation), the modes used (KW, KWP), the key encryption keys (KEKs), and the relationship to the broader key management policy.
2. Select the key wrapping mode:
   - KW: AES Key Wrap without padding. Used when the key data is a multiple of 8 bytes.
   - KWP: AES Key Wrap with Padding. Used when the key data is not a multiple of 8 bytes (and is 1 byte or larger).
3. Manage the KEKs using the project's key management discipline. KEKs must be at least as strong as the keys they wrap; prefer KEKs at AES 256 for long-lived keys.
4. Wrap the key using the chosen mode:
   - For KW: provide plaintext, KEK; receive ciphertext + integrity check (the integrity check is part of the algorithm).
   - For KWP: provide plaintext, KEK; receive ciphertext + integrity check.
5. Store or transmit the wrapped key with the integrity check. The integrity check must be verified before unwrapping.
6. Unwrap the key at the destination using the KEK and verifying the integrity check.
7. Document the wrapped keys, the KEKs, the integrity verification, and the use of the unwrapped key.

## Controls and evidence

Key wrapping controls include the documented mode selection, the KEK management, the integrity verification, and the use of the wrapped and unwrapped keys. Each wrapped key should be traceable to its KEK and its use case.

## Validation

Validation should confirm the mode is correctly implemented, the KEKs are managed per the policy, the integrity check is verified before unwrapping, and the unwrapped key is used appropriately. NIST CAVP test vectors confirm the implementation.

## Failure correction

Common failure modes: KEK is weaker than the wrapped key (correct: use a KEK at least as strong as the wrapped key); integrity check is not verified before unwrapping (correct: verify the integrity check); KW is used for non-aligned key data (correct: use KWP for non-aligned data); the unwrapped key is left in memory unnecessarily (correct: zero the unwrapped key when no longer needed).

## Limitations

NIST SP 800-38F specifies the key wrapping methods; it does not certify any implementation. The publication does not address every key protection use case (e.g., use within HSMs, where the key wrapping may be implicit). The publication does not replace asymmetric key encryption; readers should consult SP 800-56B for that.

## Scope note

This article summarizes project-neutral reference use of NIST SP 800-38F. It does not assert any specific implementation's conformance or claim any certification outcome.

## Canonical sources

- NIST SP 800-38F — Recommendation for Block Cipher Modes of Operation: Methods for Key Wrapping: https://csrc.nist.gov/publications/detail/sp/800-38f/final