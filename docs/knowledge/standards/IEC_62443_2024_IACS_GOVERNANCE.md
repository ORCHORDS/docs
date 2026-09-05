---
title: IEC 62443 Industrial Automation and Control Systems Security Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: IEC 62443 series (Industrial Automation and Control Systems / IACS Security) — IEC 62443-3-3 (System Security Requirements and Security Levels), IEC 62443-4-2 (Technical Security Requirements for IACS Components); https://www.iec.ch/cybersecurity/
---

# IEC 62443 Industrial Automation and Control Systems Security Governance

## Scope

This card governs how `orchords-docs` evaluates Industrial Automation and Control Systems (IACS) reference architectures against the IEC 62443 series. It is the reference input for any KB card that cites operational technology (OT), industrial sensors, SCADA systems, PLC controllers, or industrial IoT.

## Why this card exists

IEC 62443 is the canonical industrial cybersecurity standard. It organizes security into roles (System Integrator, Asset Owner, Service Provider, Product Supplier), system lifecycles, and Security Levels (SL-T 1 to SL-T 4) tied to threat actor capability. A KB card that cites an industrial system without binding to 62443 produces a reference architecture that the OT auditor cannot reconcile to the standard.

## Document set (subset)

- **IEC 62443-1-1** — Concepts and models.
- **IEC 62443-1-2** — Glossary.
- **IEC 62443-1-3** — System security compliance metrics.
- **IEC 62443-2-1** — Establishing an industrial automation and control system security program.
- **IEC 62443-2-2** — IACS protection levels.
- **IEC 62443-2-3** — Patch management in the IACS environment.
- **IEC 62443-2-4** — Service provider security.
- **IEC 62443-3-1** — Security technologies for IACS.
- **IEC 62443-3-2** — Security risk assessment and system design.
- **IEC 62443-3-3** — System security requirements and security levels.
- **IEC 62443-4-1** — Product development requirements.
- **IEC 62443-4-2** — Technical security requirements for IACS components.

References: `https://www.iec.ch/cybersecurity/`.

## Roles

| Role | Responsibility |
|---|---|
| Asset Owner | owns the IACS; defines security policy |
| System Integrator | designs, builds, integrates the IACS |
| Service Provider | operates or maintains the IACS |
| Product Supplier | provides the IACS components |

## Security Levels

IEC 62443 defines four target Security Levels (SL-T):

| SL-T | Threat actor |
|---|---|
| SL-T 1 | casual / coincidental |
| SL-T 2 | intentional with simple means and low resources |
| SL-T 3 | intentional with sophisticated means and moderate resources |
| SL-T 4 | intentional with sophisticated means and extensive resources (state actor) |

Each System Requirement (SR) and Requirement Enhancement (RE) maps to one or more SL-T levels. The KB reference card must declare the SL-T that the component targets.

## Foundational Requirements (FR)

| FR # | Title |
|---|---|
| FR 1 | Identification and authentication control |
| FR 2 | Use control |
| FR 3 | System integrity |
| FR 4 | Data confidentiality |
| FR 5 | Restricted data flow |
| FR 6 | Timely response to events |
| FR 7 | Resource availability |

## System Requirements (SR) — subset

| SR # | Title | Maps to |
|---|---|---|
| SR 1.1 | Human user identification | NIST SP 800-53 IA-2 |
| SR 1.2 | Software process and device identification | NIST SP 800-53 IA-3 |
| SR 1.3 | Account management | NIST SP 800-53 AC-2 |
| SR 1.4 | Identifier management | NIST SP 800-53 IA-4 |
| SR 1.5 | Authenticator management | NIST SP 800-53 IA-5 |
| SR 1.6 | Wireless access management | NIST SP 800-53 AC-18 |
| SR 1.7 | Strength of password-based authentication | NIST SP 800-53 IA-5 |
| SR 1.8 | Public key infrastructure certificates | NIST SP 800-53 IA-5 |
| SR 1.9 | Strength of public key-based authentication | NIST SP 800-53 IA-5 |
| SR 1.10 | Authenticator feedback | NIST SP 800-53 IA-6 |
| SR 1.11 | Failed login attempts | NIST SP 800-53 AC-7 |
| SR 1.12 | System use notification | NIST SP 800-53 AC-8 |
| SR 1.13 | Access via untrusted networks | NIST SP 800-53 AC-17 |
| SR 2.1 | Authorization enforcement | NIST SP 800-53 AC-3 |
| SR 2.2 | Wireless use control | NIST SP 800-53 AC-18 |
| SR 2.3 | Use control for portable and mobile devices | NIST SP 800-53 AC-19 |
| SR 2.4 | Mobile code | NIST SP 800-53 SC-18 |
| SR 2.5 | Session lock | NIST SP 800-53 AC-11 |
| SR 2.6 | Remote session termination | NIST SP 800-53 AC-12 |
| SR 2.7 | Concurrent session control | NIST SP 800-53 AC-10 |
| SR 2.8 | Auditable events | NIST SP 800-53 AU-2 |
| SR 2.9 | Audit storage capacity | NIST SP 800-53 AU-4 |
| SR 2.10 | Audit processing | NIST SP 800-53 AU-6 |
| SR 2.11 | Timestamps | NIST SP 800-53 AU-8 |
| SR 2.12 | Non-repudiation | NIST SP 800-53 AU-10 |
| SR 3.1 | Communication integrity | NIST SP 800-53 SC-8 |
| SR 3.2 | Malicious code protection | NIST SP 800-53 SI-3 |
| SR 3.3 | Security functionality verification | NIST SP 800-53 SI-7 |
| SR 3.4 | Software and information integrity | NIST SP 800-53 SI-7 |
| SR 3.5 | Input validation | NIST SP 800-53 SI-10 |
| SR 3.6 | Deterministic output | NIST SP 800-53 SI-1 |
| SR 3.7 | Error handling | NIST SP 800-53 SI-11 |
| SR 3.8 | Session integrity | NIST SP 800-53 SC-23 |
| SR 3.9 | Protection of audit information | NIST SP 800-53 AU-9 |
| SR 4.1 | Information confidentiality | NIST SP 800-53 SC-8 |
| SR 4.2 | Information persistence | NIST SP 800-53 SI-12 |
| SR 4.3 | Use of cryptography | NIST SP 800-53 SC-13 |
| SR 5.1 | Network segmentation | NIST SP 800-53 SC-7 |
| SR 5.2 | Zone boundary protection | NIST SP 800-53 SC-7 |
| SR 5.3 | General purpose person-to-person communication restrictions | NIST SP 800-53 SC-7 |
| SR 5.4 | Application partitioning | NIST SP 800-53 SC-2 |
| SR 5.5 | Zone bridging | NIST SP 800-53 SC-7 |
| SR 5.6 | Public access system segregation | NIST SP 800-53 SC-7 |
| SR 6.1 | Audit log accessibility | NIST SP 800-53 AU-6 |
| SR 6.2 | Continuous monitoring | NIST SP 800-53 CA-7 |
| SR 7.1 | DoS protection | NIST SP 800-53 SC-5 |
| SR 7.2 | Resource management | NIST SP 800-53 SC-6 |
| SR 7.3 | Control system backup | NIST SP 800-53 CP-9 |
| SR 7.4 | Control system recovery and reconstitution | NIST SP 800-53 CP-10 |
| SR 7.5 | Emergency power | NIST SP 800-53 PE-11 |
| SR 7.6 | Network and security configuration settings | NIST SP 800-53 CM-6 |
| SR 7.7 | Least functionality | NIST SP 800-53 CM-7 |
| SR 7.8 | Control system component inventory | NIST SP 800-53 CM-8 |

References: IEC 62443-3-3:2013 Am1:2024 (Annex A, SR tables).

## Zones and conduits

62443 organizes IACS into Zones and Conduits:

- **Zone** — a grouping of physical and logical assets sharing common security requirements.
- **Conduit** — a logical grouping of communication channels between zones.

Policy:

- Every Zone is assigned a target Security Level (SL-T).
- Every Conduit is assigned a target Security Level.
- Communication between Zones of different SL-T requires explicit authorization at the higher SL-T.

## Mandatory pre-flight (before adopting a new IACS component)

1. The component is assigned to a Zone and a Conduit.
2. The component's target Security Level (SL-T) is declared.
3. The applicable System Requirements are documented.
4. The component's conformance to 62443-4-2 is documented (component-level).
5. The asset owner's security program (62443-2-1) covers the component.

## Self-attestation cycle

Every 180 days:

1. Walk every IACS reference card.
2. Confirm the Security Level (SL-T) is current.
3. Confirm zones and conduits are documented.
4. Update the next-review date.

## Sources

- IEC 62443 series: `https://www.iec.ch/cybersecurity/`
- IEC 62443-3-3:2013 Am1:2024: `https://www.iec.ch/store/`
- NIST SP 800-82 (Industrial Control System Security): `https://csrc.nist.gov/publications/detail/sp/800-82/rev-3/final`
- NIS2 (EU Directive 2022/2555): `https://eur-lex.europa.eu/eli/dir/2022/2555/oj`
