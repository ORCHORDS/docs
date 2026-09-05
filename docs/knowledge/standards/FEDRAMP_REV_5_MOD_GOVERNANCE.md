---
title: "FedRAMP Rev 5 Moderate Governance"
owner: "Standards Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "FedRAMP Rev. 5 (Jul 2023 baseline alignment to NIST SP 800-53 Rev. 5); https://www.fedramp.gov/"
---

# FedRAMP Rev 5 Moderate Governance

## Purpose

FedRAMP (Federal Risk and Authorization Management Program) Rev. 5 Moderate baseline governs the authorisation of cloud services used by US federal agencies at the moderate-impact tier. The Rev. 5 baseline aligns to NIST SP 800-53 Rev. 5 control catalog, with FedRAMP overlays and parameters documented in the *FedRAMP Baseline Materials* (control families AC, AT, AU, CA, CM, CP, IA, IR, MA, MP, PE, PL, PS, RA, SA, SC, SI, SR).

## Current context and source status

Rev. 5 is the current FedRAMP baseline, aligned to NIST SP 800-53 Rev. 5 (published 2020 with subsequent updates). The Rev. 5 baseline became effective July 2023. Authorisation packages issued under the FedRAMP PMO use the SSP template + Security Assessment Plan (SAP) + Security Assessment Report (SAR) + POA&M with FedRAMP-defined parameters.

## Governance workflow and controls

1. Determine impact tier: Low, Moderate, High, or LiSaa / Tailored.
2. Build the SSP at the SSP boundary and the Moderate baseline (controls numbered Rev. 5 AC-2 through SR-12 with associated overlays and FedRAMP-defined parameters).
3. Address FedRAMP overlays (privacy overlay, continuous-monitoring overlay, supply-chain overlay).
4. Implement continuous monitoring per FedRAMP Continuous Monitoring Strategy Guide: monthly vulnerability scans (Nessus), annual / significant-change assessments, POA&M update cadence.
5. Operate the 3PAO assessment programme for initial authorisation and annual assessments (SAR delivery).
6. Document supply-chain risk management per NIST SP 800-161 Rev. 2 (VR-1 through VR-5) and per the FedRAMP supplier risk tab.
7. Maintain FedRAMP-acceptable cryptography (FIPS 140-3 / NIST SP 800-131A:2024) and FedRAMP-aligned key management (NIST SP 800-57).

## Validation and evidence

- Completed SSP at Moderate baseline with FedRAMP overlays.
- Security Assessment Report (SAR) from an accredited 3PAO.
- Authorisation decision (JAB or agency-issued ATO) recorded in the FedRAMP Marketplace.
- Monthly ConMon deliverables: vulnerability scan reports (Critical/High remediation SLAs), POA&M updates, significant-change requests.
- Incident response plan harmonised with US-CERT and FedRAMP reporting timelines.

## Failure correction

Common defects include treating Rev. 4 controls as identical to Rev. 5 (the renumbering is significant), omitting the Supply Chain (SR) family, missing FedRAMP overlays, and failing to align cryptographic modules to FIPS 140-3. Corrective actions include a Rev. 4 → Rev. 5 control mapping review and a ConMon evidence refresh.

## Limitations

- FedRAMP is US-federal; international equivalents include Australia's IRAP, the UK's Cyber Essentials Plus / G-Cloud, and the EU Cloud Computing Compliance Criteria (C5).
- ATO is agency-scoped; partner agencies inherit via P-ATO / reciprocity agreements.
- Moderate is a level, not a certification; it is one of four FedRAMP baselines.

## Canonical sources

- FedRAMP Rev. 5 baseline materials (2023).
- NIST SP 800-53 Rev. 5 (control catalog reference).
- NIST SP 800-37 Rev. 3 (RMF).
- NIST SP 800-161 Rev. 2 (supply chain).
- FedRAMP Continuous Monitoring Strategy Guide.
- FIPS 140-3 / SP 800-131A:2024.

## Scope note

This article belongs to the standards leaf and cross-references the engineering leaf for control implementation details, the operations leaf for ConMon cadences, and the risk leaf for supply-chain risk treatment.
