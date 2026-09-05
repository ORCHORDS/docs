---
title: "Firmware Integrity Verification Best Practices"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-155 (Draft 2018), NIST SP 800-193, TCG Reference; https://csrc.nist.gov/publications/detail/sp/800-193/final"
---

# Firmware Integrity Verification Best Practices

## Scope

Reference card for firmware integrity verification, drawing on NIST SP 800-193 (Platform Resiliency), NIST SP 800-155 (BIOS Integrity Measurement, draft 2018), the TCG Reference (Trusted Platform Module and Roots of Trust), and the UEFI Specification 2.10. Profiles that govern firmware integrity should reference these documents by version and bind them to the secure-boot and measured-boot workflows.

## Identifier table

| Field | Value |
| --- | --- |
| Primary documents | NIST SP 800-193 (final), NIST SP 800-155 (draft 2018), UEFI Specification 2.10, TCG Reference, TPM Library Specification 2.0 |
| Status | SP 800-193 final (Dec 2018); SP 800-155 draft 2018; UEFI 2.10 current; TCG Reference and TPM Library Specification 2.0 current |
| Companion artifacts | Secure Boot, Measured Boot, TPM 2.0, Intel TXT, AMD SVM, ARM TrustZone |
| Source URL | https://csrc.nist.gov/publications/detail/sp/800-193/final |

## Plan

1. Reference the platform-resiliency guidance (NIST SP 800-193) when governing firmware integrity verification.
2. Bind the firmware integrity workflow to the secure-boot and measured-boot controls.
3. Identify the platform root-of-trust: hardware root of trust, TPM 2.0, or vendor-proprietary root of trust.
4. Specify the firmware inventory: components, versions, signing identities, and verification records.
5. Specify the firmware update procedure: signed updates, rollback protection, and the recovery procedure.
6. Specify the detection procedure: integrity-measurement comparison, deviation handling, and recovery.
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- NIST SP 800-193 platform-resiliency controls (Protection, Detection, Recovery).
- NIST SP 800-155 draft BIOS integrity measurement controls.
- UEFI Specification 2.10 Secure Boot and Measured Boot sections.
- TPM Library Specification 2.0 — Platform Configuration Registers (PCR), attestation, and sealing.
- Internal firmware inventory, signing-key inventory, and verification tooling.

## ORCHORDS Profile

ORCHORDS treats NIST SP 800-193 as the canonical reference for platform resiliency. Profiles that reference firmware integrity should cite SP 800-193 by version, identify the platform root-of-trust, and bind to UEFI 2.10, TPM 2.0, and the secure-boot and measured-boot workflows.

A profile that references "firmware integrity" without binding to a recognized root-of-trust framework is non-conformant.

## Implementation Notes

- The SP 800-193 framework organizes controls around Protection, Detection, and Recovery; align the firmware integrity controls with this structure.
- PCR 0–7 typically cover boot state; PCRs vary by platform and boot mode. The internal PCR mapping should be documented.
- Firmware updates should be signed by the platform vendor or by a delegated signing authority; unsigned firmware is a critical security defect.
- Rollback protection prevents downgrade attacks; document the rollback policy and the minimum-supported version.
- Recovery from detected integrity failures should be a documented runbook; ad-hoc recovery is non-conformant.

## Companion Documents

- [NIST SP 800-155 BIOS Integrity Measurement](NIST_SP_800_155_BIOS_INTEGRITY_MEASUREMENT.md)
- [UEFI Specification 2.10](UEFI_SPECIFICATION_2_10.md)
- [TPM Library Specification 2.0](TPM_LIBRARY_SPECIFICATION_2_0.md)
- [TCG Reference](TCG_REFERENCE.md)
- [NIST SP 800-161 C-SCRM](NIST_SP_800_161_C_SCRM.md)
- [Secure Boot and Measured Boot Response](../playbooks/SECURE_BOOT_AND_MEASURED_BOOT_RESPONSE.md)
