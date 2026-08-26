# sales-tax-us-states

**Issue:** Handling US sales tax nexus and collection across states for SaaS
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
After South Dakota v. Wayfair (2018), economic nexus rules mean you may owe sales tax in states where you have no physical presence. SaaS taxability varies by state.

## Pattern / Solution
Use Stripe Tax, TaxJar, or Avalara to determine taxability by state and product category. Register in states where you exceed nexus thresholds. Apply the tax_code txcd_10103001 for SaaS in Stripe Tax for correct classification.

## Gotchas
SaaS is not taxable in all states. Colorado has a retail delivery fee separate from sales tax. Do not collect tax in states where you are not registered — it creates liability.

## Related
vat-calculation-eu, stripe-tax-calculation, tax-reporting-1099
