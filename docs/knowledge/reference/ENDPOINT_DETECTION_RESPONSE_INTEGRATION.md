---
title: "Endpoint Detection and Response Integration Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "MITRE ATT&CK; NIST SP 800-61 Rev. 2; NIST SP 800-83 Rev. 1 (Guide to Malware Incident Prevention); CIS Critical Security Controls"
---

# Endpoint Detection and Response Integration Reference Card

## Scope

Reference card for Endpoint Detection and Response (EDR) integration as a mechanism for continuous endpoint telemetry, behavioral detection, and response orchestration. EDR agents run on endpoints (workstations, servers, cloud workloads) and produce telemetry that feeds the SOC, the SIEM, and the SOAR. Profiles that govern endpoint security should adopt EDR coverage across all in-scope endpoints, integrate EDR with SIEM/SOAR, and bind to NIST SP 800-61 (incident handling), MITRE ATT&CK (threat framework), and the secure boot / TPM 2.0 / measured boot references.

## Identifier table

| Field | Value |
| --- | --- |
| Primary sources | MITRE ATT&CK, NIST SP 800-61 Rev. 2, NIST SP 800-83 Rev. 1, CIS Critical Security Controls |
| Companion artifacts | UEFI Specification, TPM Library Specification 2.0, NIST SP 800-155, TCG Reference |
| Source URL | https://attack.mitre.org/ |

## Plan

1. Reference EDR integration in endpoint-security policy and SOC runbooks.
2. Deploy EDR agents to all in-scope endpoints (workstations, servers, cloud workloads) with a defined coverage target (typically >95%).
3. Configure EDR telemetry to feed the SIEM with raw events and enriched alerts.
4. Map EDR detections to MITRE ATT&CK techniques for consistent analysis and reporting.
5. Configure automated response actions (for example, isolate host, kill process, quarantine file) via SOAR.
6. Tune detection rules to reduce false positives while preserving detection of true positives.
7. Maintain a documented playbook per MITRE ATT&CK tactic (Initial Access, Execution, Persistence, etc.).
8. Bind to NIST SP 800-61 Incident Handling Governance for the incident-response process.
9. Bind to Secure Boot / Measured Boot / TPM 2.0 references for the boot-time integrity context.
10. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- MITRE ATT&CK Enterprise Matrix.
- EDR platform documentation (for example, CrowdStrike, SentinelOne, Microsoft Defender for Endpoint, Carbon Black).
- SIEM and SOAR integration configuration.
- Detection-rule library and tuning records.
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats EDR integration as a foundational control for endpoint security. Profiles that govern endpoint security should deploy EDR to all in-scope endpoints, feed EDR telemetry to the SIEM, map detections to MITRE ATT&CK, automate response actions via SOAR, and bind to NIST SP 800-61 and the secure-boot references.

A profile that governs endpoint security without EDR coverage and SIEM integration is non-conformant.

## Implementation Notes

- EDR coverage should be tracked in the asset inventory; endpoints without EDR agents are a control gap.
- Detection rules should be tested against MITRE ATT&CK evaluations (for example, ATT&CK Evaluations published results) to validate efficacy.
- Automated response actions can cause operational disruption; the SOAR playbook should include a human-approval step for destructive actions.
- EDR telemetry is high-volume; the SIEM should filter and aggregate before alerting.
- EDR agents should be tamper-resistant; self-protection, kernel-level integrity, and cloud-managed control plane are best practices.

## Companion Documents

- [UEFI Specification 2.10](UEFI_SPECIFICATION_2_10.md)
- [TPM Library Specification 2.0](TPM_LIBRARY_SPECIFICATION_2_0.md)
- [NIST SP 800-155 BIOS Integrity Measurement](NIST_SP_800_155_BIOS_INTEGRITY_MEASUREMENT.md)
- [TCG Reference](TCG_REFERENCE.md)
- [Firmware Integrity Verification Best Practices](FIRMWARE_INTEGRITY_VERIFICATION_BEST_PRACTICES.md)
- [NIST SP 800-61 Incident Handling Governance](../standards/NIST_SP_800_61_INCIDENT_HANDLING_GOVERNANCE.md)
