---
title: "AICPA SOC 2 Trust Services Criteria Governance"
owner: "Standards Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "AICPA TSP Section 100, Trust Services Criteria for Security, Availability, Processing Integrity, Confidentiality, and Privacy (2017, revised 2022); https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2"
---

# AICPA SOC 2 Trust Services Criteria Governance

## Purpose

The American Institute of CPAs (AICPA) Trust Services Criteria (TSC) 2017, revised 2022, define the criteria for evaluating and reporting on the controls of a service organisation under the SOC 2 framework (System and Organisation Controls, type 2 report). The TSC covers five categories: Security, Availability, Processing Integrity, Confidentiality, and Privacy. SOC 2 is the dominant private-sector assurance baseline for SaaS / cloud service organisations.

## Current context and source status

The 2017 TSC (revised 2022) is the current version. The 2022 revisions align the Common Criteria (CC1.x through CC9.x) with the COSO internal-control framework (2013, updated 2025). The Privacy Criteria (P1.x through P8.x) remain aligned to Generally Accepted Privacy Principles (GAPP). A SOC 2 Type 2 report covers a period (typically 6-12 months); a SOC 2 Type 1 report covers a point in time.

## Governance workflow and controls

1. Determine the system description: scope of the SOC 2 system, services, components, people, processes, and locations (DC100 supplement).
2. Select applicable Trust Services Categories: Security is mandatory; Availability, Processing Integrity, Confidentiality, and Privacy are additional when relevant.
3. Implement the Common Criteria (CC1.1 – CC9.2):
   - CC1 Control environment
   - CC2 Communication and information
   - CC3 Risk assessment (aligned to COSO ERM)
   - CC4 Monitoring activities
   - CC5 Control activities
   - CC6 Logical and physical access (CC6.1 – CC6.8)
   - CC7 System operations (CC7.1 – CC7.5)
   - CC8 Change management (CC8.1)
   - CC9 Risk mitigation (CC9.1 – CC9.2)
4. Implement the Additional Criteria for each chosen category (A1.x Availability; C1.x Confidentiality; PI1.x Processing Integrity; P1–P8 Privacy).
5. Engage a CPA firm for examination; plan Type 1 (point-in-time) or Type 2 (period) per business need; align report coverage to customer MSAs.

## Validation and evidence

- System Description per DC100 (and DC200 if applicable).
- Trust Services Criteria coverage matrix: criterion → control → owner → evidence.
- Subservice organisations — inclusive vs carve-out method; review of SOC reports of subservice orgs.
- Type 2 report with opinion and findings (qualified, adverse, disclaimer).
- Complementary User Entity Controls (CUEC) and Complementary Service Organisation Controls (CSOC) clearly stated in the report.

## Failure correction

Common defects include treating CC6 / CC7 merely as logical-access control, missing subservice-organisation evaluation, and weak CC3 risk-assessment cadence. Corrective actions include a full CC coverage review, a subservice-organisation SOC report register, and a quarterly risk-assessment trigger.

## Limitations

- SOC 2 is a private-sector assurance report; it is not a public-sector attestation. Federal clients typically require FedRAMP; healthcare clients typically require HIPAA attestation on top of SOC 2.
- A SOC 2 Type 2 without exceptions is no guarantee of operational excellence; tie evidence to operational metrics (SLAs, error budgets).
- Privacy Criteria (P-series) overlap with but are not equivalent to GDPR Article 28 / ISO/IEC 27701; map them where multi-jurisdictional scope applies.

## Canonical sources

- AICPA TSP Section 100, Trust Services Criteria for Security, Availability, Processing Integrity, Confidentiality, and Privacy (2017; revised 2022).
- AICPA SOC 2 Reporting on an Examination of Controls at a Service Organisation (AT-C § 205, § 320).
- COSO Internal Control — Integrated Framework (2013).
- AICPA SOC 2 Reporting Toolkit (illustrative policies, evidence matrices).
- Cloud Security Alliance (CSA) STAR mapping for SOC 2 → CCM cross-walk.

## Scope note

This article belongs to the standards leaf and cross-references the engineering leaf for control implementation, the operations leaf for change/release gating, and the risk leaf for risk-assessment cadences.
