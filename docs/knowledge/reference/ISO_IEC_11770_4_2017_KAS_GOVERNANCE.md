# ISO/IEC 11770-4:2017 Key Establishment Using a Symmetric Technique Governance

## Purpose

ISO/IEC 11770-4:2017, "Information security — Key management — Part 4: Key establishment based on symmetric techniques," specifies key establishment mechanisms that use a symmetric technique: symmetric key agreement, key distribution, key derivation, and key transport, using a pre-shared secret or a trusted key distribution center (KDC). This article governs the application of ISO/IEC 11770-4 so key establishment in symmetric environments follows the standard's structure.

## Scope

The standard applies to any organization using symmetric key establishment. Within this knowledge base, the article covers the key establishment mechanisms (key agreement, key transport, key distribution via KDC), the pre-shared secrets, the use of KDCs (and the ticket-based schemes), and the documentation of the key establishment. It does not cover asymmetric key establishment (readers should consult ISO/IEC 11770-3 for that).

## Workflow

1. Establish the key establishment policy: scope, mechanisms, the relationship to the key management policy, and the cryptographic algorithms and parameters used.
3. Select the key establishment mechanism appropriate to the context:
   - Key agreement: both parties contribute to the derived key.
   - Key transport: one party generates the key and sends it to the other, protected by the pre-shared secret.
   - Key distribution via KDC: a third party (KDC) distributes the keys using a ticket-based scheme (Needham-Schroeder, Kerberos-style).
5. Identify the pre-shared secrets or the KDC keys. Manage them using the controls of ISO/IEC 11770-1.
4. Implement the mechanism with the appropriate cryptographic primitives: block ciphers (AES), MACs (CMAC, HMAC), and the appropriate modes of operation.
5. Perform key confirmation to verify both parties have derived the same key.
6. Document the mechanism, the parameters, the key confirmation, and the use of the established key.

## Controls and evidence

Key establishment controls include the documented mechanism, the pre-shared secret management, the KDC implementation (where used), the cryptographic primitives, the key confirmation, and the key use. Each key establishment operation should be traceable to the mechanism used.

## Validation

Validation should confirm the mechanism is correctly implemented, the pre-shared secrets are managed per the policy, the cryptographic primitives are correctly applied, the key confirmation passes, and the established key is used appropriately. Periodic review confirms the framework remains aligned with the requirements.

## Failure correction

Common failure modes: the pre-shared secret is reused for multiple purposes (correct: use distinct keys per purpose); key confirmation is skipped (correct: confirm key agreement between parties); the KDC is a single point of failure (correct: deploy the KDC with redundancy and review for compromise); the cryptographic primitives are weak (correct: use AES, HMAC, or CMAC with approved parameters).

## Limitations

ISO/IEC 11770-4 specifies the mechanisms; it does not certify any implementation. The standard does not address every symmetric key establishment context (e.g., group key agreement); readers should consult other standards for those. The standard does not prescribe specific algorithms or parameter sets; readers should select them based on the security and regulatory requirements.

## Scope note

This article summarizes project-neutral reference use of ISO/IEC 11770-4:2017. It does not assert any specific implementation's conformance or claim any certification outcome.

## Canonical sources

- ISO/IEC 11770-4:2017 — Information security — Key management — Part 4: Key establishment based on symmetric techniques: https://www.iso.org/standard/67933.html
- ISO/IEC 11770-1:2010 — Information security — Key management — Part 1: Framework: https://www.iso.org/standard/53421.html