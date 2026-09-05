---
title: "PCI DSS v4.0 Governance"
owner: "Standards Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "PCI DSS v4.0 (March 2022, future-dated requirements effective 2024/2025); https://www.pcisecuritystandards.org/"
---

# PCI DSS v4.0 Governance

## Purpose

Payment Card Industry Data Security Standard (PCI DSS) version 4.0 (March 2022) defines 12 principal requirements across 6 control objectives for entities that store, process, or transmit cardholder data (CHD) or sensitive authentication data (SAD). v4.0 supersedes v3.2.1; the future-dated requirements became enforceable for new assessments from 1 April 2025. v4.0 introduces the customized approach and the customised validation approach alongside the defined approach.

## Current context and source status

v4.0 is the current PCI DSS version. v3.2.1 retires at the close of 2024. The PCI SSC has published the v4.0 document, the ROC template (Report on Compliance), the SAQ templates (self-assessment questionnaires, A / A-EP / B / B-IP / C / C-VT / D / D-Merchant / D-Service Provider / P2PE), and accompanying information supplements (including Targeted Risk Analyses).

## Governance workflow and controls

1. Determine scope: CHD and SAD environment, system components, people, processes, locations. Apply the customised approach where v4.0 allows.
2. Implement the 12 principal requirements: Install and maintain network security controls (Req. 1); Apply secure configurations to all system components (Req. 2); Protect stored account data (Req. 3); Protect cardholder data with strong cryptography during transmission over open, public networks (Req. 4); Protect all systems and networks from malicious software (Req. 5); Develop and maintain secure systems and software (Req. 6); Restrict access to system components and cardholder data by business need to know (Req. 7); Identify users and authenticate access to system components (Req. 8); Restrict physical access to cardholder data (Req. 9); Log and monitor all access to system components and cardholder data (Req. 10); Test security of systems and networks regularly (Req. 11); Support information security with organisational policies and programs (Req. 12).
3. Address v4.0 future-dated requirements (e.g., Req. 8.3.6 password rotation; Req. 8.4.2 MFA for all access into the CDE; Req. 12.5.1 risk-based inventory; Req. 8.6.1 application/system account authentication).
4. Perform Targeted Risk Analyses where the standard explicitly requires one.
5. Conduct annual SAQ / triennial ROC assessment with a QSA (Qualified Security Assessor) for SAQ D / ROC.
6. Maintain incident response per PCI DSS Req. 12.10, aligned to NIST SP 800-61 Rev. 2.

## Validation and evidence

- Current AOC (Attestation of Compliance) or SAQ submission.
- ROC report from QSA (Level 1 merchant or service provider).
- Targeted Risk Analyses completed for applicable requirements.
- Quarterly ASV scan reports; annual penetration testing per Req. 11; internal vulnerability scans.
- Card data flow diagrams and CHD inventory.

## Failure correction

Common defects include under-scoping, failure to address future-dated requirements, and treating v3.2.1 evidence as v4.0-conformant. Corrective actions include a v3.2.1 → v4.0 delta mapping and a CDE / SAD scope re-baselining.

## Limitations

- PCI DSS is contractual; it binds merchants / service providers via the card brand agreements.
- v4.0's customised approach is fully valid but requires specialised QSA review; defined approach remains the normative reference.
- Reissued tokens / EMV / P2PE reduce but do not eliminate the CDE scope.

## Canonical sources

- PCI DSS v4.0 (March 2022).
- PCI SSC ROC / SAQ / Information Supplements.
- PCI SSC targeted risk-analysis guidance.
- PCI SSC QSA / ASV qualification programmes.

## Scope note

This article belongs to the standards leaf and cross-references the engineering leaf for technical control implementation, the operations leaf for scan cadences, and the risk leaf for scope reduction techniques.
