# ANSI X9.24-1:2017 DUKPT Derived Unique Key Per Transaction Governance

## Purpose

ANSI X9.24-1:2017, "Retail Financial Services Symmetric Key Management — Part 1: Using Symmetric Techniques," specifies symmetric key management for the financial services industry. The standard defines the Derived Unique Key Per Transaction (DUKPT) scheme used in payment terminals and PIN pads to derive a unique key for each transaction from a base derivation key (BDK), so that compromise of a single transaction key does not reveal past or future keys. This article governs the application of DUKPT and the broader ANSI X9.24-1 key management discipline.

## Scope

The standard applies to financial services organizations that use symmetric key management for retail transactions. Within this knowledge base, the article covers DUKPT concepts (BDK, initial PIN encryption key, future key request, transaction key), key lifecycle, key injection, key storage, key usage separation, and the documentation of key management. It does not cover asymmetric key management (which is addressed in other ANSI X9 parts); readers should consult those separately.

## Workflow

1. Establish the key management policy: scope, roles, responsibilities, controls, and the relationship to the payment scheme (e.g., PCI PTS requirements for PIN terminals).
2. Generate or inject the BDK using a dual-control, split-knowledge process. The BDK is shared between the acquirer and the terminal manufacturer; both must maintain it securely.
3. Inject the BDK into each terminal using a hardware security module (HSM) and a key-injection process that is PCI PTS validated. Each terminal also receives an initial key encrypted with the BDK.
4. In the terminal, derive a new transaction key for each transaction using the DUKPT derivation: the key serial number (KSN), a counter, and the DUKPT algorithm.
5. Use the transaction key only once, for one transaction. After use, the transaction key is discarded.
6. Manage key inventory, key custody, key compromise procedures, and key destruction using the controls the standard defines.

## Controls and evidence

DUKPT controls include the key management policy, the key inventory, the key-injection records, the HSM configuration, the terminal key records, the compromise procedures, and the destruction records. Each key should be traceable from generation through use to destruction.

## Validation

Validation should confirm the BDK is generated and stored under dual control, the terminals are loaded through PCI PTS validated processes, the DUKPT derivation produces unique transaction keys, the transaction keys are used once, and the key compromise procedures are tested. PCI assessments confirm compliance with the payment scheme requirements.

## Failure correction

Common failure modes: the BDK is not protected under dual control (correct: enforce dual control and split knowledge at generation and storage); transaction keys are reused (correct: enforce single-use at the terminal level and audit); key compromise procedures are untested (correct: rehearse the procedures); key inventory is not maintained (correct: maintain a current inventory with the key status); HSM is not validated (correct: use validated HSMs and PCI PTS validated injection).

## Limitations

DUKPT is one key management scheme among several defined in the standard; the choice depends on the payment context. The standard does not certify any specific implementation; PCI assessments are the operational certification. The standard does not cover asymmetric key management; readers should consult ANSI X9.42 and related parts.

## Scope note

This article summarizes project-neutral reference use of ANSI X9.24-1:2017 and the DUKPT scheme. It does not assert any specific payment implementation's conformance or claim any PCI certification outcome.

## Canonical sources

- ANSI X9.24-1:2017 — Retail Financial Services Symmetric Key Management — Part 1: Using Symmetric Techniques: https://webstore.ansi.org/standards/ascx9/ansix92412017
- PCI Security Standards Council — PIN Transaction Security: https://www.pcisecuritystandards.org/