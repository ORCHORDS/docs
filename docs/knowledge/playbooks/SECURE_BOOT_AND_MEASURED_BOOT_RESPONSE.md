---
title: "Secure Boot and Measured Boot Validation Playbook"
owner: "Endpoint Security Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-09-04"
review-cycle: "90 days"
next-review: "2026-12-03"
---

# Secure Boot and Measured Boot Validation Playbook

## Trigger

Use this playbook when endpoints, servers, or edge devices are imaged, updated, audited, or repurposed, and the integrity of the boot chain — from firmware through operating system kernel — must be established, verified, or restored.

## Scope

Apply the process to UEFI-class endpoints, servers, and embedded devices, including BIOS/UEFI firmware, bootloaders, OS loaders, kernel, initramfs, and the Trusted Platform Module (TPM) or equivalent root of trust used for measurement.

## Inputs

- device inventory and platform identity (manufacturer, model, firmware version);
- Secure Boot database (PK, KEK, db, dbx) and policy;
- measured boot PCR policy and expected reference values;
- firmware update tools and signing infrastructure;
- incident context, change ticket, or audit requirement.

## Steps

1. **Confirm platform support.** Verify the device supports UEFI 2.x, Secure Boot, and a TPM 1.2/2.0 or equivalent; record the platform identity and firmware revision.
2. **Provision the root of trust.** Initialize the TPM, set the owner authorization, generate or install the endorsement and storage keys; record the EK certificate and the PCR policy.
3. **Manage Secure Boot keys.** Maintain a controlled set of Platform Keys (PK), Key Exchange Keys (KEK), Authorized Signatures database (db), and Forbidden Signatures database (dbx); rotate on compromise or policy change.
4. **Sign boot components.** Sign bootloaders, OS loaders, and kernels using keys that are enrolled in the Secure Boot db; revoke compromised keys by adding their signatures to dbx.
5. **Enable measured boot.** Configure the firmware to extend PCRs with measurements of firmware, bootloader, OS loader, kernel, and initramfs; capture expected reference values for known-good configurations.
6. **Verify at startup.** Validate PCR values against the reference set at boot and at remote attestation; treat unexpected PCR values as a tampering indicator and trigger the incident response process.
7. **Attest remotely.** Use TPM2_Quote or equivalent to produce signed quotes of PCR values; verify the quote against the attestation server's trust anchor before granting access to secrets.
8. **Update firmware and boot components safely.** Apply firmware updates through vendor-signed channels; verify the integrity and signature of updates before applying; document the update in the device record.
9. **Respond to firmware compromise.** Treat UEFI/boot compromise as a high-severity incident: re-image from trusted media, rotate keys, re-enroll the device, and investigate root cause across the fleet.
10. **Audit and report.** Verify that all in-scope devices meet the Secure Boot and measured boot policy; report exceptions and remediation status to the security steering committee.

## Escalation

Escalate to the Endpoint Security Lead, Platform Engineering, and Incident Response when:
- a device fails Secure Boot or measured boot validation;
- a signing key is suspected of compromise;
- a firmware update is unsigned or fails signature verification;
- attestation infrastructure is unreachable beyond tolerance.

## Evidence

- Secure Boot database versions and signing key fingerprints;
- PCR reference values and current PCR values;
- TPM attestation quotes and verification logs;
- firmware update records and signature verification;
- incident response and remediation records.

## Completion Criteria

The Secure Boot and measured boot validation is considered complete when:
- the device boots only signed components;
- measured boot PCRs match the reference values;
- remote attestation succeeds;
- exceptions are documented, scoped, and tracked to remediation.

## Exceptions

Document deviations with the approver, scope, expiration, compensating control, and review schedule. Where a device cannot meet the policy, isolate it from sensitive data until remediation.

## Related Documents

- [NIST SP 800-155 BIOS Integrity Measurement](NIST_SP_800_155_BIOS_INTEGRITY_MEASUREMENT.md)
- [UEFI Specification 2.10](UEFI_SPECIFICATION_2_10.md)
- [TPM Library Specification 2.0](TPM_LIBRARY_SPECIFICATION_2_0.md)
- [Trusted Computing Group Reference](TCG_REFERENCE.md)
- [Endpoint Detection and Response Integration](ENDPOINT_DETECTION_RESPONSE_INTEGRATION.md)
