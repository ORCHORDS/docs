# iso-27018-pii-cloud

**Issue:** Implementing ISO 27018:2019 privacy controls for PII in public cloud environments
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
ISO 27018 establishes privacy-specific controls for cloud service providers processing PII. It is used alongside ISO 27001/27002 to demonstrate GDPR-compatible data processing in the cloud.

## Pattern / Solution
Key ISO 27018 control areas:

Consent and use limitation:
- Process PII only for lawful purposes specified by the cloud service customer
- Do not use PII for advertising or marketing without explicit customer instruction
- Do not use customer data to train models or improve services unless explicitly agreed

Transparency:
- Publish list of sub-processors; notify customers before adding new sub-processors
- Disclose where PII may be stored/processed geographically
- Make DPA terms publicly available

Data subject rights support:
- Provide mechanisms for customers to retrieve and delete PII
- Respond to data portability requests in machine-readable format
- Document processes for handling law enforcement requests

Security controls (extending ISO 27002):
- Temporary files deleted or anonymized after use
- PII not transmitted over unsecured networks
- Encryption of PII in transit and at rest (AES-256 minimum)
- Access to PII logged; logs available to customers

Breach notification:
- Notify cloud customer without undue delay (target: within 24 hours of discovery)
- Provide information needed for customer to meet their own breach notification obligations

Evidence for customers: CSPs certified to ISO 27018 publish annual transparency reports.

## Gotchas
- ISO 27018 certification does not substitute for GDPR DPA — still need a signed DPA
- Sub-processor notification clauses often have long notice periods (30 days) — check DPA
- Customer must audit CSP compliance — certification alone is not sufficient due diligence
- Encryption key management: if CSP holds keys, encryption provides limited protection against CSP access

## Related
- `iso-27017-cloud-security.md`
- `gdpr-international-transfers-schrems2.md`
- `vendor-security-assessment.md`
