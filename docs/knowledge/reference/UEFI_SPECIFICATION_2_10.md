---
title: "UEFI Specification 2.10"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "UEFI Specification 2.10 (August 2022); https://uefi.org/specifications"
---

# UEFI Specification 2.10

## Scope

Reference card for the Unified Extensible Firmware Interface (UEFI) Specification 2.10 (August 2022). UEFI defines the platform firmware interface for boot, runtime services, and the protocol interfaces that BIOS / firmware implementations provide. Profiles that govern firmware integrity, secure boot, measured boot, or platform initialization should reference the UEFI Specification 2.10 by version and bind to the NIST SP 800-193 platform-resiliency guidance, NIST SP 800-155 (Draft), and the TPM Library Specification 2.0.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | UEFI Specification 2.10 (August 2022) |
| Status | Current published version |
| Companion artifacts | NIST SP 800-193 (Platform Resiliency), NIST SP 800-155 (Draft, BIOS Integrity), TPM Library Specification 2.0, TCG Reference |
| Source URL | https://uefi.org/specifications |

## Plan

1. Reference UEFI Specification 2.10 by version whenever a profile governs UEFI firmware, secure boot, measured boot, or platform initialization.
2. Identify the UEFI implementation: vendor, version, security database (db, dbx, KEK, PK), and the secure-boot mode (deployed, setup).
3. Specify the secure-boot policy: which signers are trusted, which signatures are revoked, and the rotation procedure for the security database.
4. Specify the measured-boot policy: PCR usage, measurement log, and the response to measured values that deviate from the baseline.
5. Specify the firmware update procedure: signed capsule updates, rollback protection, and recovery from failed updates.
6. Specify the runtime services that the OS relies on (variable services, time services, reset services) and the expected behaviour.
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- UEFI Specification 2.10 sections relevant to the platform (boot services, runtime services, protocol interfaces, security database).
- Platform vendor implementation guide.
- NIST SP 800-193 (Protection, Detection, Recovery).
- NIST SP 800-155 (Draft, BIOS Integrity Measurement).
- TPM Library Specification 2.0.

## ORCHORDS Profile

ORCHORDS treats UEFI Specification 2.10 as the canonical reference for UEFI platform firmware. Profiles that reference UEFI should cite the version, identify the platform-specific implementation, and bind to NIST SP 800-193 and TPM 2.0.

A profile that references "firmware" or "BIOS" without binding to UEFI 2.10 (or successor) is non-conformant.

## Implementation Notes

- The UEFI security database (PK, KEK, db, dbx) is the trust anchor for secure boot; rotation of db and dbx requires planning.
- Measured boot requires a TPM 2.0 device and an OS / firmware combination that supports PCR measurement logs.
- UEFI Capsule Update is the standard update mechanism; the capsule should be signed by the platform vendor.
- UEFI runtime services include variable services (used for NVRAM), which the OS uses for boot configuration; access control and auditing should be considered.
- Older platforms may still ship with legacy BIOS; the profile should identify legacy BIOS scenarios separately from UEFI.

## Companion Documents

- [Firmware Integrity Verification Best Practices](FIRMWARE_INTEGRITY_VERIFICATION_BEST_PRACTICES.md)
- [NIST SP 800-155 BIOS Integrity Measurement](NIST_SP_800_155_BIOS_INTEGRITY_MEASUREMENT.md)
- [NIST SP 800-161 C-SCRM](NIST_SP_800_161_C_SCRM.md)
- [Secure Boot and Measured Boot Response Playbook](../playbooks/SECURE_BOOT_AND_MEASURED_BOOT_RESPONSE.md)
