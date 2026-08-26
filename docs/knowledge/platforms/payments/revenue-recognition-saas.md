# revenue-recognition-saas

**Issue:** Recognizing SaaS subscription revenue correctly over the service period per ASC 606
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cash received for annual subscriptions is deferred revenue, not recognized immediately. Revenue is recognized ratably over the subscription period. Incorrect recognition causes misstated financials.

## Pattern / Solution
On subscription creation, create a deferred_revenue record for the full prepaid amount. Each month, run a job that moves the proportional amount from deferred to recognized. For Stripe, use invoice line item period.start and period.end to determine recognition window.

## Gotchas
Upgrades and downgrades trigger proration — recognize the prorated amounts for each period separately. Refunds require reversing recognized revenue. Use Stripe Revenue Recognition to automate this rather than building manually.

## Related
mrr-arr-calculation, stripe-proration-logic, stripe-upgrade-downgrade, accounting-integration-quickbooks
