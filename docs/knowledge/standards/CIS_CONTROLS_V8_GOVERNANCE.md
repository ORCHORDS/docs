---
title: CIS Critical Security Controls v8 Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: Center for Internet Security (CIS) Critical Security Controls v8 (May 2021) — https://www.cisecurity.org/controls/v8
---

# CIS Critical Security Controls v8 Governance

## Scope

This card governs how `orchords-docs` evaluates cybersecurity controls against CIS Critical Security Controls v8 (CIS CSC v8). It is the reference input for any KB card that describes a defensive control or a recommended practice.

## Why this card exists

CIS CSC v8 organizes defensive controls into 18 control families, each containing Implementation Groups (IG1 / IG2 / IG3) tied to organization size and capability. Without an explicit card, the KB cites defensive controls that do not survive a CIS-aligned audit.

## Document set

- **CIS Critical Security Controls v8** (May 2021) — the canonical defensive-controls framework.
- **CIS Benchmarks** — platform-specific hardening (Ubuntu, Windows, Kubernetes, etc.).
- **CIS Community Defense Model** — adversary-driven mapping to controls.

References: `https://www.cisecurity.org/controls/v8`.

## The 18 Controls

| Control # | Title |
|---|---|
| 1 | Inventory and Control of Enterprise Assets |
| 2 | Inventory and Control of Software Assets |
| 3 | Data Protection |
| 4 | Secure Configuration of Enterprise Assets and Software |
| 5 | Account Management |
| 6 | Access Control Management |
| 7 | Continuous Vulnerability Management |
| 8 | Audit Log Management |
| 9 | Email and Web Browser Protections |
| 10 | Malware Defenses |
| 11 | Data Recovery |
| 12 | Network Infrastructure Management |
| 13 | Network Monitoring and Defense |
| 14 | Security Awareness and Skills Training |
| 15 | Service Provider Management |
| 16 | Application Software Security |
| 17 | Incident Response Management |
| 18 | Penetration Testing |

## Implementation Groups

Each Safeguard is assigned to one or more Implementation Groups (IGs):

| IG | Description |
|---|---|
| IG1 | small organizations, essential cyber hygiene |
| IG2 | mid-size organizations, NIST CSF 800-171-aligned |
| IG3 | mature organizations, NIST CSF 800-53-aligned |

The project targets IG2 as the minimum baseline for KB reference cards.

## Sub-controls (subset)

The project tracks the following high-impact Safeguards (per CIS CSC v8):

| Safeguard | Title |
|---|---|
| 1.1 | Establish and Maintain Detailed Enterprise Asset Inventory |
| 2.1 | Establish and Maintain a Software Inventory |
| 3.1 | Establish and Maintain a Data Management Process |
| 3.11 | Encrypt Sensitive Data at Rest |
| 4.1 | Establish and Maintain a Secure Configuration Process |
| 5.1 | Establish and Maintain an Inventory of Accounts |
| 5.4 | Restrict Administrator Privileges to Dedicated Administrator Accounts |
| 6.1 | Establish an Access Granting Process |
| 6.7 | Centralize Access Control |
| 7.1 | Establish and Maintain a Vulnerability Management Process |
| 8.1 | Establish and Maintain an Audit Log Management Process |
| 8.11 | Conduct Audit Log Reviews |
| 9.x | Email and Web Browser Protections |
| 10.1 | Deploy and Maintain Anti-Malware Software |
| 11.1 | Establish and Maintain a Data Recovery Process |
| 12.1 | Ensure Network Infrastructure is Up-to-Date |
| 13.1 | Centralize Security Event Alerting |
| 14.1 | Establish and Maintain a Security Awareness Program |
| 15.1 | Establish and Maintain Service Provider Inventory |
| 16.1 | Establish and Maintain a Secure Application Development Process |
| 17.1 | Designate Personnel to Manage Incident Handling |
| 18.1 | Establish and Maintain a Penetration Testing Program |

## Mapping to other standards

| Standard | Mapping |
|---|---|
| NIST CSF 2.0 | per CSF v8 crosswalk |
| NIST SP 800-53 Rev. 5 | per NIST crosswalk |
| ISO/IEC 27001:2022 | per ISO/IEC mapping |
| PCI-DSS | per PCI-DSS mapping |
| HIPAA | per HIPAA mapping |

References: `https://www.cisecurity.org/controls/v8/mappings`.

## Mandatory pre-flight (before adopting a new defensive control)

1. The applicable CIS Control and Safeguard is identified.
2. The target Implementation Group is declared.
3. The control is implemented and tested.

## Cross-reference

| Domain | Card |
|---|---|
| NIST CSF | `NIST_CSF_2_2024_GOVERNANCE.md` |
| NIST 800-53 | `NIST_SP_800_53A_REV5_ASSESSMENT_GOVERNANCE.md` |
| ISO 27001 | (deferred) |
| Logging | `NIST_SP_800_92_LOG_GOVERNANCE.md` |
| Vulnerability mgmt | `ISO_IEC_30111_2019_VDP_GOVERNANCE.md` |

## Self-attestation cycle

Every 180 days:

1. Walk every KB reference card.
2. Confirm the CIS CSC mapping is current.
3. Update the next-review date.

## Sources

- CIS Critical Security Controls v8: `https://www.cisecurity.org/controls/v8`
- CIS Benchmarks: `https://www.cisecurity.org/cis-benchmarks`
- CIS Community Defense Model: `https://www.cisecurity.org/insights/blog/cdm`
- CIS Implementation Groups: `https://www.cisecurity.org/controls/v8/implementation-groups`
