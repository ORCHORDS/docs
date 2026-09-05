---
title: "TPM Library Specification 2.0"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "TCG TPM Library Specification 2.0 (TCG); https://trustedcomputinggroup.org/resource/tpm-library-specification/"
---

# TPM Library Specification 2.0

## Scope

Reference card for the TCG TPM Library Specification 2.0. The specification defines the Trusted Platform Module (TPM 2.0) — the hardware root of trust used for platform integrity measurement, key sealing, remote attestation, and platform identity. Profiles that govern hardware-rooted trust, measured boot, secure boot, key sealing, or remote attestation should reference TPM 2.0 by version and bind to NIST SP 800-155 (Draft), NIST SP 800-193, UEFI 2.10, and the TCG Reference.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | TCG TPM Library Specification 2.0 (current published revision) |
| Status | Maintained by the Trusted Computing Group |
| Companion artifacts | TCG Reference, NIST SP 800-193 (Platform Resiliency), NIST SP 800-155 (Draft), UEFI 2.10, TCG PC Client Platform TPM Profile |
| Source URL | https://trustedcomputinggroup.org/resource/tpm-library-specification/ |

## Plan

1. Reference the TCG TPM Library Specification 2.0 by version whenever a profile governs hardware-rooted trust.
2. Identify the TPM 2.0 part: discrete TPM, integrated TPM (fTPM), or firmware TPM; the security guarantees vary by part type.
3. Specify the TPM usage model: PCR usage for integrity measurement, key sealing to PCR values, remote attestation (TPM 2.0 attestation), and the authorization policy.
4. Specify the PCR allocation and the expected values for boot integrity measurement; deviations from the baseline trigger the response procedure.
5. Specify the key hierarchy: endorsement, storage, platform, attestation, and the endorsement-key management policy.
6. Specify the remote-attestation procedure: attestation identity, nonce handling, signed attestation, and the verifier workflow.
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- TCG TPM Library Specification 2.0 sections relevant to the platform.
- Platform vendor implementation guide.
- NIST SP 800-193, NIST SP 800-155 (Draft), UEFI 2.10.
- Internal PCR baseline, key-hierarchy inventory, and attestation records.

## ORCHORDS Profile

ORCHORDS treats the TCG TPM Library Specification 2.0 as the canonical reference for hardware-rooted trust. Profiles that reference TPM should cite the version, identify the part type, and bind to NIST SP 800-193 and UEFI 2.10.

A profile that references "hardware root of trust" without binding to TPM 2.0 (or successor) is non-conformant.

## Implementation Notes

- The endorsement key (EK) is the TPM's identity; protect the EK privacy per the platform vendor guidance.
- PCR allocation differs by platform and boot mode (UEFI, legacy); the internal PCR baseline should reflect the actual platform.
- Key sealing to PCR values enables decryption only when the boot state is correct; this is the foundation of platform-bound key release.
- Remote attestation requires a verifier that can validate the attestation; the verifier-side policy should be documented.
- TPM 2.0 hardware is the most secure part type; firmware TPMs (fTPM) are easier to deploy but have a different threat model.

## Companion Documents

- [Firmware Integrity Verification Best Practices](FIRMWARE_INTEGRITY_VERIFICATION_BEST_PRACTICES.md)
- [NIST SP 800-155 BIOS Integrity Measurement](NIST_SP_800_155_BIOS_INTEGRITY_MEASUREMENT.md)
- [UEFI Specification 2.10](UEFI_SPECIFICATION_2_10.md)
- [TCG Reference](TCG_REFERENCE.md)
- [Secure Boot and Measured Boot Response Playbook](../playbooks/SECURE_BOOT_AND_MEASURED_BOOT_RESPONSE.md)
