# PCI DSS Payment-Page Script Inventory and Tamper Detection

**Issue:** Unauthorized browser scripts or modifications to e-commerce pages can skim payment data even when card fields are hosted by a payment processor.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Inventory every script authorized on payment pages, record its purpose and owner, and justify why it is necessary.
- Assure script integrity and authorization using controls appropriate to first- and third-party delivery.
- Deploy change- and tamper-detection for payment-page content and security-impacting HTTP headers with actionable alerting.
- Treat the merchant page surrounding an embedded payment iframe as security-relevant when its scripts can affect the transaction.
- Retain evidence supporting PCI DSS 4.0.1 Requirements 6.4.3 and 11.6.1 or the applicable SAQ A eligibility confirmation.

## Verification

- Introduce an unauthorized script and a modified authorized script in a test page; both must be detected.
- Verify the inventory against rendered production pages, tag managers, consent managers, and dynamically loaded dependencies.
- Exercise alert delivery, triage ownership, and evidence retention.

## Gotchas

- Verify source maturity and product support before making a normative claim.
- Keep secrets, tokens, personal data, and restricted evidence out of examples and logs.
- Reassess after material changes to scope, dependencies, or enforcement.

## Sources

- https://blog.pcisecuritystandards.org/new-information-supplement-payment-page-security-and-preventing-e-skimming
- https://www.pcisecuritystandards.org/faqs/1588/
- https://blog.pcisecuritystandards.org/important-updates-announced-for-merchants-validating-to-self-assessment-questionnaire-a
