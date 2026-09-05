---
title: "NIST Cybersecurity Framework 2.0 Governance"
owner: "Standards Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST CSF 2.0 (February 2024); https://www.nist.gov/cyberframework"
---

# NIST Cybersecurity Framework 2.0 Governance

## Purpose

NIST Cybersecurity Framework (CSF) 2.0, published February 26, 2024, provides a taxonomy of cybersecurity outcomes and a common language for managing cybersecurity risk across sectors and organisational roles. CSF 2.0 introduces the GOVERN function, expands the scope beyond critical infrastructure, and integrates with NIST SP 800-53 Rev. 5, NIST SP 800-171 Rev. 3, and the NIST Privacy Framework. Profiles that claim CSF alignment should bind to 2.0 explicitly.

## Current context and source status

CSF 2.0 (final) is the current version. The companion Quick-Start Guides (QSG) cover the six functions (GOVERN, IDENTIFY, PROTECT, DETECT, RESPOND, RECOVER) plus QSG profiles for small businesses, enterprises, and ransomware risk management. CSF 1.1 remains valid for legacy contracts; new implementations should adopt 2.0.

## Governance workflow and controls

1. Align the organisational profile to one or more CSF 2.0 profiles (enterprise profile, small-business profile, or sector profile such as the Ransomware Risk Management: A Cybersecurity Framework 2.0 Profile).
2. Map each Govern/Identify/Protect/Detect/Respond/Recover subcategory to existing controls (NIST SP 800-53 Rev. 5 controls, ISO/IEC 27002:2022 Annex A controls, sector-specific overlays).
3. Establish the GOVERN function deliverables: organisational context (GV.OC), risk management strategy (GV.RM), roles & responsibilities (GV.RR), policies & procedures (GV.PO), oversight (GV.OV), cybersecurity supply chain risk management (GV.SC).
4. Maintain a current target profile, current profile, and prioritised gap remediation plan (PR.IP-12, ID.RA, GV.RM).
5. Tie CSF outcomes to risk-tier and impact-tier posture (FIPS 199 / NIST SP 800-60).
6. Use the CSF Tiers (Partial, Risk-Informed, Repeatable, Adaptive: GV.OV-01 / ID.AM) to inform organisational risk posture.

## Validation and evidence

- Organisational target / current / gap profiles with version stamps.
- Mapping matrix CSF subcategory → internal control → owner → evidence.
- GOVERN function deliverables including supply-chain risk management oversight.
- Tier assessment rationale and board-level reporting cadence.

## Failure correction

Common defects include mapping only Protect/Detect/Respond subcategories and omitting the GOVERN function; or treating the CSF as a compliance checklist rather than a risk-informed posture. Corrective actions include completing the GOVERN subcategory coverage and re-baselining target vs current profile against updated threat intelligence.

## Limitations

- CSF 2.0 is a framework of outcomes, not a checklist of mandatory controls.
- Tier assessments are self-declared; external assurance requires explicit ties to SP 800-53A or ISO/IEC 27001 / 27002 attestations.
- CSF 2.0 is sector-agnostic; sector overlays (e.g., NIST SP 800-171 Rev. 3 for CUI) should be combined where applicable.

## Canonical sources

- NIST Cybersecurity Framework 2.0, 2024.
- NIST CSF Quick-Start Guides (GOVERN, IDENTIFY, PROTECT, DETECT, RESPOND, RECOVER; Enterprise, SMB, Ransomware profiles).
- NIST SP 800-53 Rev. 5 (controls mapping).
- NIST SP 800-171 Rev. 3 (CUI profile mapping).
- NIST Privacy Framework 1.0 (privacy mapping).

## Scope note

This article belongs to the standards leaf and cross-references the engineering leaf for implementation specifics, the operations leaf for cadences, and the risk leaf for tier assessment rationale.
