---
title: "NIST SP 800-155 BIOS Integrity Measurement"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-155 (December 2011, Draft); https://csrc.nist.gov/publications/detail/sp/800-155/draft"
---

# NIST SP 800-155 BIOS Integrity Measurement

## Scope

Reference card for NIST Special Publication 800-155 (Draft, December 2011), *BIOS Integrity Measurement Guidelines (Draft)*. The draft remains the primary NIST reference for BIOS / firmware integrity measurement even though it has not been finalized. Profiles that govern BIOS / firmware integrity should reference SP 800-155 (Draft) and bind it to NIST SP 800-193 (Platform Resiliency), the UEFI Specification 2.10, the TPM Library Specification 2.0, and the secure-boot and measured-boot workflows.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | NIST SP 800-155 (Draft, December 2011) |
| Status | Draft (no finalized revision as of September 2026) |
| Companion artifacts | NIST SP 800-193 (Platform Resiliency), UEFI Specification 2.10, TPM Library Specification 2.0, TCG Reference |
| Source URL | https://csrc.nist.gov/publications/detail/sp/800-155/draft |

## Plan

1. Reference SP 800-155 (Draft) by version whenever a profile governs BIOS / firmware integrity measurement.
2. Establish the BIOS integrity baseline: known-good images, known-good measurements, and the integrity-measurement mechanism.
3. Apply the BIOS update procedure: signed updates, rollback protection, and recovery from failed updates.
4. Apply the integrity-measurement procedure: PCRs (TPM 2.0), measurement comparison, and the response to integrity failures.
5. Bind to NIST SP 800-193 (Protection, Detection, Recovery) for the broader platform-resiliency framework.
6. Bind to UEFI 2.10 and TPM 2.0 for the protocol-level specifications.
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- SP 800-155 (Draft) sections: 3 (BIOS integrity), 4 (measurement), 5 (update), 6 (recovery).
- NIST SP 800-193 (Platform Resiliency), UEFI 2.10, TPM 2.0.
- Internal BIOS inventory, signed-image inventory, and integrity-measurement tooling.

## ORCHORDS Profile

ORCHORDS treats SP 800-155 (Draft) as the canonical NIST reference for BIOS integrity measurement. Profiles that reference BIOS / firmware integrity should cite the draft by version, identify the integrity-measurement mechanism, and bind to NIST SP 800-193 and the platform-level specifications.

A profile that references "BIOS integrity" without binding to a recognized framework is non-conformant.

## Implementation Notes

- BIOS updates should be signed by the platform vendor or by a delegated signing authority; unsigned BIOS updates are a critical security defect.
- Rollback protection prevents downgrade attacks; document the rollback policy and the minimum-supported version.
- PCR values for BIOS measurements should be recorded as part of the integrity baseline; ad-hoc baselines are non-conformant.
- Recovery from integrity failures should be a documented runbook; ad-hoc recovery is non-conformant.
- The BIOS integrity measurement should be verified at every boot, not only at provisioning.

## Companion Documents

- [Firmware Integrity Verification Best Practices](FIRMWARE_INTEGRITY_VERIFICATION_BEST_PRACTICES.md)
- [NIST SP 800-161 C-SCRM](NIST_SP_800_161_C_SCRM.md)
- [Secure Boot and Measured Boot Response Playbook](../playbooks/SECURE_BOOT_AND_MEASURED_BOOT_RESPONSE.md)
