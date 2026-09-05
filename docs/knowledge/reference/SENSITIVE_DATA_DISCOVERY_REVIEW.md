---
title: "Sensitive Data Discovery Review Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-60 Rev. 1; NIST SP 800-137; ISO/IEC 27001 Annex A.5.12–A.5.13; ISO 27701"
---

# Sensitive Data Discovery Review Reference Card

## Scope

Reference card for sensitive data discovery, the practice of scanning data stores (databases, file shares, object stores, document repositories) to detect unclassified or misclassified sensitive data. Discovery uses pattern matching (for example, regex for SSNs, credit cards, IBANs), named-entity recognition for PII, and machine-learning models for unstructured data. Profiles that govern information protection should adopt a discovery tooling strategy, schedule regular scans, and bind to the data-classification review, ISO 27701 privacy-information management, and GDPR breach-notification guidance.

## Identifier table

| Field | Value |
| --- | --- |
| Primary sources | NIST SP 800-60 Rev. 1, NIST SP 800-137 (Information Security Continuous Monitoring), ISO/IEC 27001 Annex A.5.12–A.5.13, ISO 27701 |
| Companion artifacts | Data Classification Review, ISO 27701 Privacy Information Management, GDPR Article 33 |
| Source URL | https://csrc.nist.gov/pubs/sp/800/60/v1/r1/final |

## Plan

1. Reference sensitive-data discovery in data-classification policy and discovery tooling strategy.
2. Inventory data stores (databases, file shares, object stores, document repositories) and apply a discovery cadence per classification.
3. Use a combination of pattern matching (regex), named-entity recognition, and ML models for unstructured data.
4. Score findings by sensitivity and exposure; prioritize remediation by score.
5. Define a remediation workflow: classify, tag, restrict access, encrypt, or delete.
6. Maintain audit records of discovery scans, findings, and remediation actions.
7. Bind to Data Classification Review for the classification scheme and remediation workflow.
8. Bind to ISO 27701 Privacy Information Management for the PII context.
9. Bind to GDPR Article 33 for breach-notification when unclassified Restricted data is discovered.
10. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- Data-classification scheme and labels.
- Data-store inventory with location, owner, and data-format metadata.
- Discovery tooling configuration (for example, Microsoft Purview, AWS Macie, Google Cloud DLP, Collibra, BigID).
- Remediation workflow and ticketing system.
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats sensitive data discovery as a foundational control for information protection. Profiles that govern information protection should inventory data stores, apply discovery tooling with pattern matching and NER, score findings by sensitivity, remediate per a defined workflow, maintain audit records, and bind to the Data Classification Review, ISO 27701, and GDPR Article 33.

A profile that governs information protection without discovery tooling is non-conformant.

## Implementation Notes

- Pattern matching alone produces false positives and misses context-aware PII; combine with NER and ML.
- Discovery cadence should be higher for high-risk stores (for example, monthly) and lower for low-risk stores (for example, quarterly).
- Discovery findings should be tracked to closure; untracked findings are a control gap.
- Sensitive data in test environments should be de-identified or synthesized; discovery should confirm test environments are clean.
- Discovery results should be auditable; the audit trail supports regulatory inquiries and breach notifications.

## Companion Documents

- [Data Classification Review](DATA_CLASSIFICATION_REVIEW.md)
- [ISO 27701 Privacy Information Management](ISO_27701_PRIVACY_INFORMATION_MANAGEMENT.md)
- [GDPR Article 33 Breach Notification](GDPR_ARTICLE_33_BREACH_NOTIFICATION.md)
- [NIST SP 800-53 Rev. 5 Access Control Family](NIST_SP_800_53_REV_5_ACCESS_CONTROL_FAMILY.md)
