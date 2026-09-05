---
title: NIST Cybersecurity Framework 2.0 Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: NIST Cybersecurity Framework 2.0 (February 2024) — https://www.nist.gov/cyberframework; NIST CSF 2.0 Reference Tool; NIST SP 800-53 Rev. 5 crosswalk
---

# NIST Cybersecurity Framework 2.0 Governance

## Scope

This card governs how `orchords-docs` evaluates the NIST Cybersecurity Framework 2.0 (CSF 2.0). It is the reference input for any KB card that touches cybersecurity governance, risk assessment, or control mapping.

## Why this card exists

NIST CSF 2.0 organizes cybersecurity into six Functions: Govern, Identify, Protect, Detect, Respond, Recover. The "Govern" function is new in 2.0. The KB cards must align with CSF 2.0 to survive a CSF-aligned audit.

## Document set

- **NIST CSF 2.0** (February 2024) — Core, Tiers, Profile.
- **NIST CSF 2.0 Reference Tool** — online.
- **NIST SP 800-53 Rev. 5** — crosswalk.

References: `https://www.nist.gov/cyberframework`.

## Six Functions

| Function | Description |
|---|---|
| Govern | establish and monitor the cybersecurity risk management strategy |
| Identify | understand the organization's assets, risks, and vulnerabilities |
| Protect | implement safeguards to ensure delivery of critical services |
| Detect | find and analyze cybersecurity events |
| Respond | take action regarding detected cybersecurity events |
| Recover | restore capabilities and services impaired by a cybersecurity event |

## Categories and Subcategories

CSF 2.0 defines 22 Categories (one new category in Govern) and 106 Subcategories. The KB reference card enumerates the applicable Categories per reference architecture.

### Govern

| Category | Title |
|---|---|
| GV.OC | Organizational Context |
| GV.RM | Risk Management Strategy |
| GV.SC | Cybersecurity Supply Chain Risk Management |
| GV.RR | Roles, Responsibilities, and Authorities |
| GV.PO | Policies, Processes, and Procedures |
| GV.OV | Oversight |
| GV.MT | Continuous Monitoring |

### Identify

| Category | Title |
|---|---|
| ID.AM | Asset Management |
| ID.RA | Risk Assessment |
| ID.IM | Improvement |

### Protect

| Category | Title |
|---|---|
| PR.AA | Identity, Authentication, and Access Control |
| PR.AT | Awareness and Training |
| PR.DS | Data Security |
| PR.PS | Platform Security |
| PR.IR | Technology Infrastructure Resilience |

### Detect

| Category | Title |
|---|---|
| DE.AE | Anomalies and Events |
| DE.CM | Continuous Monitoring |
| DE.DP | Detection Processes |

### Respond

| Category | Title |
|---|---|
| RS.RP | Response Planning |
| RS.CO | Communications |
| RS.AN | Analysis |
| RS.MI | Mitigation |
| RS.IM | Improvements |

### Recover

| Category | Title |
|---|---|
| RC.RP | Recovery Planning |
| RC.IM | Improvements |
| RC.CO | Communications |

References: `https://www.nist.gov/cyberframework`.

## Tiers

CSF 2.0 defines four Tiers:

| Tier | Description |
|---|---|
| 1 — Partial | ad-hoc, reactive |
| 2 — Risk-Informed | risk management practices approved but not enterprise-wide |
| 3 — Repeatable | formal policies, enterprise-wide |
| 4 — Adaptive | continuous improvement, advanced |

The KB reference card declares the Tier that each reference architecture targets.

## Profile

A CSF Profile is the alignment of Categories and Subcategories with the organization's mission, risk tolerance, and resources. Profiles are organization-specific; the KB documents the project's profile.

## Mandatory pre-flight (before adopting a new cybersecurity control)

1. The applicable Function and Category are identified.
2. The applicable Subcategory is identified.
3. The Target Tier is declared.
4. The current profile is updated.

## Cross-reference

| Domain | Card |
|---|---|
| Risk | `ISO_IEC_27005_2022_RISK_GOVERNANCE.md` |
| Network | `ISO_IEC_27033_2022_NETWORK_GOVERNANCE.md` |
| Incident | `ISO_IEC_27035_2016_INCIDENT_GOVERNANCE.md` |
| Identity | `NIST_SP_800_63_3_DIGITAL_IDENTITY_GOVERNANCE.md` |
| Supply chain | `NIST_CSWP_23_2024_SSB_GOVERNANCE.md` |

## Self-attestation cycle

Every 180 days:

1. Walk every KB reference card.
2. Confirm the CSF 2.0 mapping is current.
3. Confirm the profile is updated.
4. Update the next-review date.

## Sources

- NIST CSF 2.0: `https://www.nist.gov/cyberframework`
- NIST CSF 2.0 Reference Tool: `https://csrc.nist.gov/Projects/cybersecurity-framework`
- NIST SP 800-53 Rev. 5: `https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final`
- NIST SP 800-53B (Control Baselines): `https://csrc.nist.gov/publications/detail/sp/800-53b/final`
