# NIST SP 800-71 TPM 2.0 Governance

## Purpose

NIST SP 800-71, "Trusted Platform Module (TPM) 2.0 Security Guidelines," provides guidance on the deployment and use of TPM 2.0 in platforms. The TPM is a hardware security module integrated into a platform that provides secure storage of secrets, platform integrity measurement, cryptographic operations, and attestation. This article governs the application of NIST SP 800-71 so TPM 2.0 is used in a way that meets the security objectives the publication defines.

## Scope

The publication applies to platforms that use TPM 2.0. Within this knowledge base, the article covers TPM 2.0 functionality (TPM hierarchy, PCRs, key types, sealed data, attestation), the security objectives the TPM supports (sealing, binding, attestation, identity), the deployment guidance (initialization, ownership, hierarchy selection), and the documentation of TPM usage. It does not cover a specific TPM vendor's implementation; readers should consult the platform's TPM documentation.

## Workflow

1. Establish the TPM usage policy: scope, hierarchy selection, key types used, attestation use cases, and the relationship to platform integrity.
2. Initialize the TPM during platform provisioning. Set the platform hierarchy authorization (consider disabling the platform hierarchy if it not is needed) and the endorsement hierarchy.
3. Establish the platform's integrity measurement chain: the BIOS/UEFI measurements, the bootloader, the OS, and the application layer. Each layer extends a PCR with the measurement of the next layer.
4. Use TPM key types appropriate to the use case:
   - Endorsement Key (EK): identity, used in attestation.
   - Attestation Identity Keys (AIKs): signing attestation quotes.
   - Storage keys: protect other keys.
   - Sealing keys: bind data to PCR values.
5. Use sealing to protect data that should only be released when the platform is in a known state (PCR values match the policy).
6. Use attestation (TPM2_Quote) to provide evidence of the platform state to a verifier.
7. Document the TPM configuration, the key types, the PCR policy, and the attestation flow.

## Controls and evidence

TPM controls include the documented configuration, the hierarchy authorization, the PCR policy, the key lifecycle, and the attestation records. Each TPM operation should be traceable to the TPM and the configuration.

## Validation

Validation should confirm the TPM is initialized, the hierarchies are configured per policy, the PCRs are extended by the boot chain, the sealing policy releases data only at expected PCR values, and the attestation verifies the platform state. TPM conformance to the TCG specification can be verified by TPM tools.

## Failure correction

Common failure modes: the TPM is not initialized (correct: initialize during provisioning with the policy hierarchy authorization); PCRs are extended without a measurement chain (correct: ensure each layer extends PCRs from the measured previous layer); the platform hierarchy remains enabled with default authorization (correct: set a strong authorization or disable the hierarchy); sealing keys are created without a PCR policy (correct: define the PCR policy that gates the unsealing).

## Limitations

NIST SP 800-71 provides guidance; it does not certify any TPM implementation. The TPM is one of several platform integrity technologies (DICE, Intel SGX); the choice depends on the platform and the security objectives. The TPM does not by itself protect against all threats (e.g., physical attacks on the platform); readers should consider the broader platform security.

## Scope note

This article summarizes project-neutral reference use of NIST SP 800-71 for TPM 2.0. It does not assert any specific platform's conformance or claim any certification outcome.

## Canonical sources

- NIST SP 800-71 — Trusted Platform Module (TPM) 2.0 Security Guidelines: https://csrc.nist.gov/publications/detail/sp/800-71/final
- TCG — TPM 2.0 Library: https://trustedcomputinggroup.org/resource/tpm-library-specification/