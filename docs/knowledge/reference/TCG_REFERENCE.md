---
title: "TCG Reference — Trusted Computing Group Architecture"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "Trusted Computing Group (TCG) Architecture; https://trustedcomputinggroup.org/"
---

# TCG Reference — Trusted Computing Group Architecture

## Scope

Reference card for the Trusted Computing Group (TCG) architecture, which underpins TPM 2.0, secure boot, measured boot, self-encrypting drives, and platform identity. Profiles that govern hardware-rooted trust, secure boot, measured boot, attestation, or platform identity should reference the TCG architecture and bind to the TPM Library Specification 2.0, NIST SP 800-193, NIST SP 800-155 (Draft), and UEFI 2.10.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | TCG architecture and specifications (current published versions) |
| Status | Continuously maintained by the Trusted Computing Group |
| Companion artifacts | TPM Library Specification 2.0, TCG PC Client Platform TPM Profile, NIST SP 800-193, NIST SP 800-155 (Draft), UEFI 2.10 |
| Source URL | https://trustedcomputinggroup.org/ |

## Plan

1. Reference the TCG architecture when governing hardware-rooted trust.
2. Identify the TCG components in use: TPM 2.0, secure boot, measured boot, self-encrypting drives (SED), network-attached TPM, or vendor-proprietary.
3. Specify the platform integrity baseline: PCR usage, key hierarchy, and the response to integrity deviations.
4. Specify the attestation procedure: attestation identity, nonce handling, signed attestation, and the verifier workflow.
5. Specify the cryptographic binding: keys sealed to PCR values, keys sealed to authorization, and the lifecycle expectations.
6. Specify the update and recovery procedure: signed firmware updates, rollback protection, and the documented recovery procedure.
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- TCG architecture overview and the relevant TCG specifications.
- TPM Library Specification 2.0.
- Platform vendor implementation guide.
- NIST SP 800-193, NIST SP 800-155 (Draft), UEFI 2.10.

## ORCHORDS Profile

ORCHORDS treats the TCG architecture as the canonical reference for hardware-rooted trust. Profiles that reference TCG should cite the relevant TCG specifications, identify the platform components, and bind to NIST SP 800-193 and UEFI 2.10.

A profile that references "hardware root of trust" without binding to TCG (or successor) is non-conformant.

## Implementation Notes

- The TCG architecture is platform-agnostic; the platform vendor implementation provides the concrete guarantees.
- Different TCG specifications cover different components: TPM 2.0, self-encrypting drives (Opal), network-attached TPM, and others.
- The TCG attestation model separates the attester (TPM) from the verifier (relying party); the verifier policy is part of the deployment.
- The TCG endorsement key is the TPM's identity; EK management varies by platform and by the privacy requirements.
- Integration with the OS: BitLocker (Windows), tpm2-tools (Linux), and other OS-level tooling provide the user-space interface.

## Companion Documents

- [Firmware Integrity Verification Best Practices](FIRMWARE_INTEGRITY_VERIFICATION_BEST_PRACTICES.md)
- [TPM Library Specification 2.0](TPM_LIBRARY_SPECIFICATION_2_0.md)
- [NIST SP 800-155 BIOS Integrity Measurement](NIST_SP_800_155_BIOS_INTEGRITY_MEASUREMENT.md)
- [UEFI Specification 2.10](UEFI_SPECIFICATION_2_10.md)
- [NIST SP 800-161 C-SCRM](NIST_SP_800_161_C_SCRM.md)
- [Secure Boot and Measured Boot Response Playbook](../playbooks/SECURE_BOOT_AND_MEASURED_BOOT_RESPONSE.md)
