# Stripe invoice rendering-template governance

**Issue:** Teams change a Stripe invoice rendering template as if it were harmless styling, unintentionally altering customer-facing tax, payment, or legal presentation.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

Invoice rendering templates are governed presentation configuration. Assign them deliberately, preview representative invoices, and retain application-side records of the approved template/version policy; rendered documents must still reconcile to authoritative invoice data.

**Source:** [Stripe invoice rendering templates](https://docs.stripe.com/invoicing/customize/invoice-rendering-template)

## Controls

- separate test and live template identifiers and keep them out of client code;
- review branding, locale, tax identifiers, payment instructions, footer/legal text, and custom fields;
- define whether assignment occurs at customer, subscription, or invoice workflow boundaries;
- restrict template changes with least privilege and audit the approver and rollout cohort;
- archive generated invoices according to accounting and retention requirements.

## Verification

- previews cover currencies, zero/negative adjustments, taxes, discounts, long descriptions, and multiple locales;
- PDF and hosted-invoice views reconcile totals and required identifiers;
- missing/deactivated template behavior is tested before rollout;
- webhook processing uses invoice object fields, never scraped rendered text.

## Gotchas

- template presentation does not alter the underlying charge or ledger semantics.
- a preview is not a finalized tax document.
- dashboard edits can bypass code review; monitor configuration changes.
