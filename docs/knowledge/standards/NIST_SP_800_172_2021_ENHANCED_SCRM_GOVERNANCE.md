# NIST SP 800-172 Enhanced Security Requirements for Controlled Unclassified Information Governance

## 1. Scope

This card governs ORCHORDS adoption of NIST SP 800-172 ("Enhanced Security Requirements for Protecting Controlled Unclassified Information (CUI) in Nonfederal Systems and Organizations") for systems that store, process, or transmit CUI and are subject to enhanced controls beyond NIST SP 800-171 Rev. 3.

## 2. Normative references

- NIST SP 800-172 (Feb 2021) — Enhanced requirements.
- NIST SP 800-171 Rev. 3 (Sept 2024) — Protecting CUI.
- NIST SP 800-53 Rev. 5 (Sept 2020) — Security and privacy controls.
- NIST SP 800-161 Rev. 1 (Apr 2022) — C-SCRM.
- DFARS 252.204-7012 (US DoD flowdown).

## 3. Enhanced requirement families

| Family | Title | Example control |
| --- | --- | --- |
| Access Control | 3.1.x | Multi-factor authentication for privileged access |
| Awareness & Training | 3.2.x | Insider threat training annually |
| Audit & Accountability | 3.3.x | Real-time audit log correlation |
| Configuration Management | 4.x | Centralised config management |
| Identification & Authentication | 5.x | Automated account management |
| Incident Response | 6.x | Incident response plan tested annually |
| Maintenance | 7.x | Non-local maintenance only via secure channels |
| Media Protection | 8.x | Media sanitisation per NIST SP 800-88 |
| Personnel Security | 9.x | Re-screening for high-risk roles |
| Physical Protection | 10.x | Physical access lists reviewed quarterly |
| Risk Assessment | 11.x | Supply chain risk assessment annually |
| System & Services Acquisition | 12.x | Continuous monitoring of COTS vendors |
| System & Communications Protection | 13.x | Cryptographic mechanisms for all CUI in transit |
| System & Information Integrity | 14.x | Threat hunting program |

## 4. Application to ORCHORDS

- CUI handling systems MUST be identified in the ORCHORDS asset inventory.
- Any system processing CUI MUST satisfy the SP 800-172 requirements within 90 days of identification.
- A SCRM plan MUST be on file with CISO sign-off for any CUI system using a third-party processor.

## 5. Implementation evidence

- Evidence MUST be captured per the ORCHORDS Security Control Matrix.
- A system security plan (SSP) MUST be on file per NIST SP 800-18 Rev. 1.
- A Plan of Action & Milestones (POAM) MUST track any in-progress requirements.

## 6. Continuous monitoring

- Quarterly review of POAMs by the CISO.
- Annual third-party assessment for any system processing > 1000 CUI records.
- Real-time audit log correlation with SOC tooling.

## 7. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-07. New NIST SP 800-172 edition or a material change to the CUI program triggers out-of-cycle updates.
