# ANSI X9.24-2:2018 PIN Key Management Governance

## Purpose

ANSI X9.24-2:2018, "Retail Financial Services Symmetric Key Management — Part 2: Using Asymmetric Techniques," specifies the use of asymmetric (public key) techniques for retail financial services, including key management for PIN translation, PIN verification, and key exchange. The standard supports the symmetric techniques of ANSI X9.24-1 by providing an asymmetric layer for key exchange and PIN protection. This article governs the application of ANSI X9.24-2 in conjunction with the symmetric techniques of Part 1, so the organization's PIN and key management follows the standard's structure.

## Scope

The standard applies to retail financial services organizations that use asymmetric techniques in conjunction with symmetric techniques. Within this knowledge base, the article covers the asymmetric key management (key pair generation, certificate issuance, key exchange), the integration with the symmetric scheme, the use of asymmetric techniques for PIN translation and verification, and the documentation of the asymmetric layer. It does not replace the symmetric techniques of Part 1; the two parts are used together.

## Workflow

1. Establish the asymmetric key management policy: scope, roles, responsibilities, key pair lifecycle, certificate management, and the integration with the symmetric scheme.
2. Generate key pairs using validated hardware (HSM). The private key must remain in the HSM or be encrypted under a key it does not reveal; the public key is published.
3. Issue certificates for public keys using a documented certificate authority (internal or external).
4. Use asymmetric techniques where the standard defines:
   - PIN translation: encrypt the PIN under the recipient's public key (RSA-OAEP, etc.).
   - PIN verification: sign or verify the PIN block.
   - Key exchange: use the asymmetric technique to exchange a symmetric key for the session.
5. Manage the key pair lifecycle: rotation, revocation, archival, and destruction. Apply the controls the standard defines for each.
6. Integrate the asymmetric layer with the symmetric scheme of Part 1: the keys exchanged through the asymmetric layer are used in the symmetric operations the organization performs.

## Controls and evidence

Asymmetric key management controls include the key generation records, the certificate records, the key exchange logs, the key lifecycle records, and the HSM configuration. Each key should be traceable from generation through use to destruction.

## Validation

Validation should confirm the key pairs are generated using validated HSMs, the certificates are valid and current, the asymmetric techniques are correctly applied, the integration with the symmetric scheme is correct, and the key lifecycle is documented. PCI assessments and external audits confirm compliance.

## Failure correction

Common failure modes: private keys are not protected in the HSM (correct: enforce HSM-resident keys and use them without export); certificates are not validated before use (correct: validate certificates at each use); key rotation is not performed (correct: rotate per the policy); the asymmetric layer is integrated incorrectly with the symmetric scheme (correct: review the integration against the standard).

## Limitations

ANSI X9.24-2 specifies the use of asymmetric techniques; it does not prescribe specific algorithms (RSA, ECC) — readers should select algorithms appropriate to the payment context. The standard does not certify any implementation. Asymmetric techniques have larger key sizes and slower operations than symmetric techniques; the standard supports the use of asymmetric techniques where the use case justifies them.

## Scope note

This article summarizes project-neutral reference use of ANSI X9.24-2:2018. It does not assert any specific implementation's conformance or claim any certification outcome.

## Canonical sources

- ANSI X9.24-2:2018 — Retail Financial Services Symmetric Key Management — Part 2: Using Asymmetric Techniques: https://webstore.ansi.org/standards/ascx9/ansix92422018
- PCI Security Standards Council — PIN Transaction Security: https://www.pcisecuritystandards.org/