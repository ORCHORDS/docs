# pci-dss-scope-reduction

**Issue:** Reducing PCI DSS compliance scope by ensuring card data never touches your servers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
If raw card data passes through your servers, you are in PCI DSS scope for the full set of requirements. Using Stripe.js with hosted fields keeps card data out of scope.

## Pattern / Solution
Use Stripe.js or Stripe Elements on the frontend — card data is tokenized in the browser and sent directly to Stripe. Your server only receives a payment_method token. Never log request bodies that might contain card data. Use Stripe Checkout for maximum scope reduction.

## Gotchas
Even with Stripe.js, if you accept card data via any other channel such as phone or email, you expand scope. SAQ A eligibility requires all cardholder data functions to be handled by a PCI-compliant third party. Review your SAQ type annually with a QSA.

## Related
pci-dss-saq-a-compliance, tokenization-vault-patterns, payment-data-retention
