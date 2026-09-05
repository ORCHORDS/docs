---
title: "Data Classification Review Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-60 Rev. 1; ISO/IEC 27001 Annex A.5.12–A.5.13; CIS Critical Security Controls"
---

# Data Classification Review Reference Card

## Scope

Reference card for data classification, the practice of assigning labels to data assets based on sensitivity, regulatory scope, and required protection. Common labels include Public, Internal, Confidential, and Restricted, with corresponding controls for access, transmission, storage, and disposal. Profiles that govern information protection should adopt a classification scheme, apply it to data assets, and bind to NIST SP 800-60 Rev. 1, ISO 27701 Privacy Information Management, the Sensitive Data Discovery Review, and GDPR Article 33 breach-notification guidance.

## Identifier table

| Field | Value |
| --- | --- |
| Primary sources | NIST SP 800-60 Rev. 1, ISO/IEC 27001 Annex A.5.12–A.5.13, ISO 27701, GDPR Art. 32–33 |
| Companion artifacts | Sensitive Data Discovery Review, ISO 27701 Privacy Information Management, GDPR Article 33 |
| Source URL | https://csrc.nist.gov/pubs/sp/800/60/v1/r1/final |

## Plan

1. Reference data classification in information-classification policy and data-handling procedures.
2. Adopt a classification scheme: Public, Internal, Confidential, Restricted (or equivalent levels appropriate to the organization).
3. Assign data owners for each data asset; the owner is accountable for the classification.
4. Define controls per classification level for access, transmission, storage, and disposal.
5. Apply sensitive-data-discovery tooling to detect unclassified or misclassified data.
6. Bind to NIST SP 800-60 Rev. 1 for the system-security categorization context.
7. Bind to ISO 27701 Privacy Information Management for PII handling.
8. Bind to Sensitive Data Discovery Review for the discovery tooling and processes.
9. Bind to GDPR Article 33 for breach-notification requirements when Restricted data is involved.
10. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- NIST SP 800-60 Rev. 1 (Guide for Mapping Types of Information and Information Systems to Security Categories).
- Data-classification policy and data-handling procedures.
- Data-asset inventory and ownership records.
- Sensitive-data-discovery tooling configuration.
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats data classification as a foundational control for information protection. Profiles that govern information protection should adopt a classification scheme, assign data owners, define controls per level, apply sensitive-data-discovery tooling, and bind to NIST SP 800-60, ISO 27701, Sensitive Data Discovery, and GDPR Article 33.

A profile that governs information protection without a documented classification scheme is non-conformant.

## Implementation Notes

- Classification labels should be machine-readable (for example, file metadata, database column tags) to enable automated enforcement.
- Classification should be applied at creation; retrofitting classification to existing data requires discovery tooling and is more expensive.
- Data owners are accountable for classification accuracy; classification should be reviewed at a defined cadence.
- Restricted data typically requires encryption at rest and in transit, strong access control, audit logging, and disposal verification.
- Regulatory scope (for example, GDPR, HIPAA, PCI DSS) may impose additional constraints beyond the classification label.

## Companion Documents

- [Sensitive Data Discovery Review](SENSITIVE_DATA_DISCOVERY_REVIEW.md)
- [ISO 27701 Privacy Information Management](ISO_27701_PRIVACY_INFORMATION_MANAGEMENT.md)
- [GDPR Article 33 Breach Notification](GDPR_ARTICLE_33_BREACH_NOTIFICATION.md)
- [NIST SP 800-53 Rev. 5 Access Control Family](NIST_SP_800_53_REV_5_ACCESS_CONTROL_FAMILY.md)
- [ISO/IEC 27001:2022 ISMS Version Guide](ISO_IEC_27001_2022_ISMS_VERSION_GUIDE.md)
