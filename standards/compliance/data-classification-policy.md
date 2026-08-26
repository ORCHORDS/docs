# data-classification-policy

**Issue:** Defining a data classification scheme and enforcing handling controls per tier across a SaaS engineering organisation
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without data classification, teams apply inconsistent security controls — encrypting low-risk config files while leaving PII in plaintext logs. Classification is a prerequisite for many compliance frameworks (ISO 27001 A.5.12, SOC 2 CC6.1, PCI DSS Req 3, HIPAA §164.312). This entry defines a practical four-tier model and the controls that attach to each tier.

## Pattern / Solution
**Four-tier classification model:**

| Tier | Label | Examples | Handling |
|---|---|---|---|
| 1 | **Public** | Marketing copy, product docs, open-source code | No restrictions |
| 2 | **Internal** | Internal wikis, meeting notes, non-PII configs | Internal access only; no public posting |
| 3 | **Confidential** | PII, customer data, API keys, audit logs | Encrypted at rest & transit; access-controlled; audit logged |
| 4 | **Restricted** | PHI, PCI PAN, credentials, legal privilege, M&A data | All Confidential controls + MFA + DLP + quarterly access review |

**Tagging at the data store level:**
```yaml
# Example: S3 bucket tagging
Tags:
  data_classification: "confidential"
  contains_pii: "true"
  retention_days: "365"
  owner_team: "backend"
```

**Enforcement controls by tier:**

```
Tier 3 (Confidential):
  - Encryption at rest: KMS-managed keys, key rotation every 90 days
  - Encryption in transit: TLS 1.2+
  - Access: IAM role-based; no wildcard (*) policies
  - Logging: CloudTrail / equivalent for all read/write operations
  - Backup: Encrypted; same classification as source

Tier 4 (Restricted):
  - All Tier 3 controls, plus:
  - MFA required for all access
  - DLP scanning on egress (email, upload, API)
  - Network: VPC with no public endpoints; private subnets only
  - Access review: Quarterly; revoke all access on role change
  - Break-glass access: Logged and alerted in real-time
```

**Developer guidance — classifying new data:**
```python
# Before adding a new database column or API field, ask:
# 1. Does this identify or describe a specific person? → Confidential minimum
# 2. Could this data be used for financial fraud? → Restricted
# 3. Is this health, legal, or biometric data? → Restricted
# 4. Will this be visible outside the organisation? → Check Tier 1/2 criteria
```

**ROPA integration:** Every processing activity in the Record of Processing Activities should reference the data classification tier for each data category.

## Gotchas
- Classification must be applied at **creation** time, not retrospectively — implement it in your data model review process.
- Downgrading classification requires documented approval; it cannot be done unilaterally to reduce compliance burden.
- Aggregate data can re-identify individuals — classified low-tier aggregate data may need to be reclassified if combined with other datasets.
- Vendor and contractor access must respect classification tiers — contractually and technically.
- DLP tools produce false positives; tune policies before blocking rather than monitoring.

## Related
- `gdpr-data-retention-policy.md`
- `hipaa-phi-handling.md`
- `pci-dss-v4-saas.md`
- `privacy-by-design-checklist.md`
- `audit-log-mandatory.md`
