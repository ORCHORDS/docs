---
title: NIST SP 800-53 Rev. 5 Security and Privacy Controls Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: NIST SP 800-53 Rev. 5 (September 2020) — Security and Privacy Controls for Information Systems and Organizations; https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final
---

# NIST SP 800-53 Rev. 5 Security and Privacy Controls Governance

## Scope

This card governs how `orchords-docs` evaluates security and privacy controls against NIST SP 800-53 Rev. 5. It is the reference input for any KB card that cites federal controls, FISMA, FedRAMP, or the security-and-privacy control families.

## Why this card exists

NIST SP 800-53 Rev. 5 is the canonical US federal security-and-privacy control catalogue. It supersedes Rev. 4 with privacy controls consolidated into the same family taxonomy and reorganized into 20 control families. A KB card that cites NIST controls without binding to Rev. 5 produces a controls mapping that does not survive a federal audit.

## Document set

- **NIST SP 800-53 Rev. 5** (September 2020) — the canonical catalogue.
- **NIST SP 800-53B** (October 2020) — control baselines (low / moderate / high).
- **NIST SP 800-53A Rev. 5** (January 2022) — assessment procedures.
- **NIST SP 800-53 Rev. 5 Errata** (updates).

References: `https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final`, `https://csrc.nist.gov/publications/detail/sp/800-53b/final`.

## 20 control families

| Family | Title |
|---|---|
| AC | Access Control |
| AT | Awareness and Training |
| AU | Audit and Accountability |
| CA | Assessment, Authorization, and Monitoring |
| CM | Configuration Management |
| CP | Contingency Planning |
| IA | Identification and Authentication |
| IR | Incident Response |
| MA | Maintenance |
| MP | Media Protection |
| PE | Physical and Environmental Protection |
| PL | Planning |
| PM | Program Management |
| PS | Personnel Security |
| PT | PII Processing and Transparency |
| RA | Risk Assessment |
| SA | System and Services Acquisition |
| SC | System and Communications Protection |
| SI | System and Information Integrity |
| SR | Supply Chain Risk Management |

References: NIST SP 800-53 Rev. 5 § 2.

## Control baselines

NIST SP 800-53B defines baselines for:

- Low-impact systems.
- Moderate-impact systems.
- High-impact systems.

Each baseline selects a subset of controls and assignments.

References: `https://csrc.nist.gov/publications/detail/sp/800-53b/final`.

## Privacy controls (PT family)

Rev. 5 consolidates privacy controls into the same catalogue:

| Control | Title |
|---|---|
| PT-1 | Policy and Procedures |
| PT-2 | Authority to Process PII |
| PT-3 | PII Processing Purposes |
| PT-4 | PII Processing Consistency |
| PT-5 | Privacy Notice |
| PT-6 | System of Records Notice |
| PT-7 | Specific Categories of PII |
| PT-8 | Computer Matching Requirements |

## Control structure

Each control has:

- `Control` — the statement.
- `Discussion` — context.
- `Related Controls` — cross-references.
- `Control Enhancements` — additional controls (e.g., `-1`, `-2`).

Example: `AC-2(1)` is `AC-2` with enhancement `(1)`.

## Mapping to other standards

| Standard | Mapping |
|---|---|
| ISO/IEC 27001:2022 | per ISO mapping |
| CIS CSC v8 | per CIS mapping |
| NIST CSF 2.0 | per CSF mapping |
| NIST SSDF v1.1 | per SSDF mapping |
| PCI-DSS v4 | per PCI mapping |

## Mandatory pre-flight (before adopting a new security or privacy control)

1. The control family and identifier are identified.
2. The applicable baseline is determined (low / moderate / high).
3. The control is implemented.
4. The control is assessed (per SP 800-53A).
5. The control is monitored.

## Cross-reference

| Domain | Card |
|---|---|
| Assessment | `NIST_SP_800_53A_REV5_ASSESSMENT_GOVERNANCE.md` |
| CSF | `NIST_CSF_2_2024_GOVERNANCE.md` |
| CIS CSC | `CIS_CONTROLS_V8_GOVERNANCE.md` |
| SSDF | `NIST_SP_800_218_SSDF_GOVERNANCE.md` |
| Privacy | `ISO_IEC_27701_2019_PIMS_GOVERNANCE.md` |

## Self-attestation cycle

Every 180 days:

1. Walk every KB reference card.
2. Confirm the SP 800-53 Rev. 5 mapping is current.
3. Confirm the baseline is declared.
4. Update the next-review date.

## Sources

- NIST SP 800-53 Rev. 5: `https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final`
- NIST SP 800-53B: `https://csrc.nist.gov/publications/detail/sp/800-53b/final`
- NIST SP 800-53A Rev. 5: `https://csrc.nist.gov/publications/detail/sp/800-53a/rev-5/final`
- NIST OSCAL: `https://pages.nist.gov/OSCAL/`
