# pci-dss-saq-a-compliance

**Issue:** Completing SAQ A (Self-Assessment Questionnaire A) for merchants using hosted payment pages
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
SAQ A is the simplest PCI compliance path for e-commerce merchants who outsource all cardholder data functions to a compliant third party like Stripe. It requires annual self-assessment.

## Pattern / Solution
Confirm eligibility: card-not-present only, all payment pages fully hosted by PCI-compliant processor, no card data stored or transmitted through your systems. Complete SAQ A questionnaire annually. Maintain a written security policy. Train staff handling payment queries.

## Gotchas
Custom checkout implementations that load card fields in an iframe from a non-PCI domain may not qualify for SAQ A. If you store any cardholder data even encrypted, you move to SAQ D. Review the PCI SSC website for the latest SAQ A requirements.

## Related
pci-dss-scope-reduction, tokenization-vault-patterns, payment-data-retention
