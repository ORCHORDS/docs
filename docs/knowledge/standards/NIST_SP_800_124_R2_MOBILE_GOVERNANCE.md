# NIST SP 800-124 Rev. 2 (2023) Mobile Device Security Governance

## 1. Scope
This document establishes governance requirements for enterprise mobile device security derived from NIST Special Publication 800-124 Rev. 2. It applies to all organizational units operating mobile endpoints, including smartphones, tablets, and ruggedised handhelds, regardless of ownership model. The controls herein govern bring-your-own-device (BYOD), choose-your-own-device (CYOD), and corporate-owned, personally-enabled (COPE) deployments and align with federal and commercial compliance frameworks as enumerated in [Section 2](#2-normative-references).

## 2. Normative references
- NIST SP 800-124 Rev. 2 (2023) Guidelines for Managing the Security of Mobile Devices in the Enterprise
- [NIST SP 800-53 Rev. 5 Control Catalog Governance](NIST_SP_800_53_R5_2_CONTROL_CATALOG_GOVERNANCE.md)
- NIST SP 800-63B authenticators governance
- ISO/IEC 27001:2022 Information Security Management
- CIS Mobile Benchmark v1.0

## 3. Terms and definitions
MDM (Mobile Device Management): administrative framework enforcing device-level policy, configuration, and telemetry across enrolled endpoints.
MAM (Mobile Application Management): controls applied to individual applications, including wrapping, per-app VPN, and selective wipe.
UEM (Unified Endpoint Management): integrated management plane spanning mobile, desktop, IoT, and wearables under a single policy fabric.

## 4. Background
Mobile endpoints increasingly access regulated data outside perimeter controls. SP 800-124 Rev. 2 supersedes Rev. 1 by elevating the mobile threat landscape, requiring continuous device posture assessment, and codifying expectations for application vetting, containerization, and centralised telemetry. The publication positions UEM as the central integration substrate that unifies device, application, identity, and threat signals per NIST SP 800-53 Rev. 5 control families AC, SI, and CM.

## 5. Mobile device security baselines
BYOD: employee-owned hardware accessing corporate data. Minimum controls: enrollment gate, container isolation, conditional access, and remote selective wipe of managed data only.
CYOD: employee-selected from an approved catalogue. Minimum controls: hardware attestation, baseline OS version, and kernel integrity verification.
COPE: corporate-owned with dual persona. Minimum controls: full device management, separation of work and personal containers, and hardware-backed credentials per NIST SP 800-63B AAL2.

## 6. Enterprise mobility deployment models
Organizations shall classify each device under one ownership archetype at enrollment. Each archetype maps to a control profile in the central policy catalogue. Reclassification requires security review and ticket audit trail; see [Section 7](#7-uemmdmmam-control-mapping) for control assignment.

## 7. UEM/MDM/MAM control mapping
MDM governs whole-device policy: OS version, patch level, encryption state, jailbreak and root attestation, remote lock, and full wipe. MDM is required for COPE deployments and any device holding regulated data on the device itself.
MAM governs application-scoped policy: app-level encryption, copy-paste restrictions, per-app single sign-on, and selective wipe of corporate data without touching personal content. MAM is required for BYOD where full device control is unacceptable to the employee.
UEM is the unifying control plane that emits both MDM and MAM instructions and ingests posture signals from identity providers, endpoint detection agents, and Mobile Threat Defence SDKs. UEM is required when an organization operates more than fifty managed endpoints or spans two or more operating-system families.

## 8. Application vetting, containerization, and SDK management
Public-store applications require vetting against the organization's allow-list, malware scan, and software bill-of-materials review. In-house applications shall be signed and distributed through an enterprise channel. Containerization separates corporate and personal data planes using either OS-provided work profiles or vendor-managed containers. SDK inventory shall be maintained with version, licence, and data-handling notes; deprecated SDKs are prohibited in production builds.

## 9. Data protection: encryption at rest and in transit, secure enclave, key store
All managed endpoints shall enforce AES-256 encryption at rest with keys bound to hardware-backed keystores (Secure Enclave on Apple platforms, StrongBox and Trusted Execution Environment on Android). Data in transit shall traverse TLS 1.3 with certificate pinning for corporate applications. Key material shall not leave the secure element except under approved export ceremonies; rotation cadence aligns with NIST SP 800-53 Rev. 5 SC-12.

## 10. Threat detection and SOAR (Security Orchestration Automation and Response) integration
Mobile Threat Defence (MTD) sensors shall forward indicators, including network anomalies, sideloaded applications, OS integrity loss, and behavioural anomalies, to the central SIEM. SOAR playbooks shall enrich UEM signals, automatically quarantine non-compliant devices, revoke tokens via the identity provider, and open incident tickets. SOAR integration is mandatory for organizations handling regulated data, and playbooks shall be tested quarterly as described in [Section 13](#13-review-cadence).

## 11. Compliance evidence (HIPAA, GDPR, PCI DSS, FedRAMP)
Evidence packages shall include enrollment records, posture snapshots, encryption attestations, and incident timelines. HIPAA: PHI access on mobile requires containerization and remote wipe proof. GDPR: data subject deletion requests trigger managed-app selective wipe within thirty days. PCI DSS: mobile point-of-sale terminals enforce tamper-evident boot and point-to-point encryption. FedRAMP: UEM solutions shall operate at Moderate or High baseline with continuous monitoring artefacts.

## 12. Risk register
R-001 Lost or stolen device exposure. Mitigation: full-disk encryption plus remote wipe within twenty-four hours.
R-002 Sideloaded malicious application. Mitigation: allow-list enforcement plus MTD behavioural monitoring.
R-003 OS version drift. Mitigation: UEM-enforced patch service-level agreements of fourteen days for critical CVEs.
R-004 Insecure network usage. Mitigation: per-app VPN with certificate pinning.
R-005 Insider data exfiltration via container bypass. Mitigation: data-loss-prevention watermarking plus egress logging.

## 13. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.