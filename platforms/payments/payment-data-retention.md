# payment-data-retention

**Issue:** Defining retention policies for payment records to meet legal requirements and minimize breach exposure
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Payment records must be retained for tax and legal purposes but storing excess data increases breach impact. Different jurisdictions have different minimum retention periods.

## Pattern / Solution
Retain transaction records (amount, date, last4, customer ID, description) for 7 years minimum per US tax law. Delete or anonymize full card data immediately after tokenization. For EU customers, apply GDPR right-to-erasure to non-financial personal data while retaining transaction records for legal compliance.

## Gotchas
GDPR right-to-erasure does not override tax and AML record-keeping requirements — retain transaction records even after erasure requests. Document your retention policy in a privacy notice. Anonymize rather than delete where full deletion is not required.

## Related
pci-dss-scope-reduction, payment-audit-logging, tokenization-vault-patterns
