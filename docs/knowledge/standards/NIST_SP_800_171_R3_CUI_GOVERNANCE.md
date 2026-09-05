---
title: "NIST SP 800-171 Rev 3 CUI Governance"
owner: "Standards Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-171 Rev. 3 (May 2024); https://csrc.nist.gov/publications/detail/sp/800-171/rev-3/final"
---

# NIST SP 800-171 Rev 3 CUI Governance

## Purpose

NIST Special Publication 800-171 Revision 3, *Protecting Controlled Unclassified Information in Nonfederal Systems and Organizations* (May 2024), defines 97 security requirements organised into 14 control families for protecting the confidentiality of CUI in nonfederal systems. Nonfederal organisations handling CUI under federal contracts (FAR 52.204-21 / DFARS 252.204-7012) must satisfy SP 800-171 Rev. 3 explicitly.

## Current context and source status

Rev. 3 is the current version (final, May 2024). It supersedes Rev. 2 (February 2020) and reorganises the requirements into 14 families aligned with NIST SP 800-53 Rev. 5. The companion CMM (Cybersecurity Maturity Model Certification) and the assessment guide (NIST SP 800-171A) align with Rev. 3.

## Governance workflow and controls

1. Establish the CUI inventory and boundary (3.1 Access Control family: AC.L1-b.1.i through AC.L3-3.2.x).
2. Apply the 14 families: Access Control, Awareness & Training, Audit & Accountability, Assessment, Authorization & Monitoring (renamed from Configuration Management/MA), Configuration Management, Identification & Authentication, Incident Response, Maintenance, Media Protection, Personnel Security, Physical Protection, Risk Assessment, Security Assessment, System & Communications Protection, System & Information Integrity.
3. For each requirement, identify the safeguarding method: prescribed requirement (must implement where CUI is resident), NCO (nonfederal organisation option), or organisational-defined parameter.
4. Maintain a System Security Plan (SSP) at the CUI boundary and any enclave scoping.
5. Maintain POA&M (Plan of Action & Milestones) for any requirement not yet fully implemented; align with DFARS 252.204-7012 (or its successor) for incident-reporting obligations.
6. Apply the assessment guide NIST SP 800-171A Rev. 3 (assessment objectives, determination statements, assessment methods examine/interview/test).

## Validation and evidence

- CUI asset / boundary inventory.
- SSP aligned to SP 800-171 Rev. 3 control families.
- Assessment report per NIST SP 800-171A Rev. 3 (or CMMC assessment by a C3PAO where CMMC applies).
- POA&M with completion dates and severity ratings.
- Evidence per requirement (policy, procedure, configuration, audit log) retained for the assessment cycle.

## Failure correction

Common defects include treating SSP and POA&M as one-time artefacts, omitting the Assessment, Authorization & Monitoring family (Configuration / MA alignment with SP 800-53 Rev. 5), and orphan POA&M items. Corrective actions: SSP refresh on every material change; POA&M review on a defined cadence with explicit closure criteria.

## Limitations

- SP 800-171 Rev. 3 is the CUI baseline; sector-specific overlays (CNSSI 1253, CMMC) may impose additional requirements.
- NCO variables allow organisational tailoring; alignment must be documented in the SSP.
- The assessment (Rev. 3) is not a certification; CMMC level 2 / 3 attestations are separate programmes.

## Canonical sources

- NIST SP 800-171 Rev. 3 (final, 2024).
- NIST SP 800-171A Rev. 3 (assessment guide).
- NIST SP 800-53 Rev. 5 (control catalog reference).
- NIST SP 800-66 Rev. 2 (HIPAA Security Rule mapping).
- DFARS 252.204-7012 (Safeguarding Covered Defense Information).
- CNSSI 1253 (federal overlay baseline).

## Scope note

This article belongs to the standards leaf and cross-references the engineering leaf for boundary implementation, the operations leaf for assessment cadence, and the risk leaf for POA&M risk-tiering.
