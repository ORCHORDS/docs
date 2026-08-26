# vat-calculation-eu

**Issue:** Calculating and collecting EU VAT correctly for digital services sold to EU customers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
EU VAT rules require charging VAT based on the customer's country of residence, not the seller's. Rates vary by country. B2B sales with valid VAT numbers are zero-rated.

## Pattern / Solution
Use Stripe Tax or a dedicated provider like TaxJar or Avalara to automate EU VAT. For manual: collect customer country, look up rate from a maintained table, validate VAT numbers via VIES API for B2B exemption, apply tax to the invoice line. Report quarterly via OSS from July 2021.

## Gotchas
UK is no longer part of the EU VAT system post-Brexit — it has its own rules. Digital services threshold of 10000 EUR annual revenue determines whether home-country or customer-country rates apply. Store evidence of customer location for 10 years.

## Related
stripe-tax-calculation, sales-tax-us-states, tax-reporting-1099, invoice-generation-pdf
