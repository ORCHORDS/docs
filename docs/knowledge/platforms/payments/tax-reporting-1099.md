# tax-reporting-1099

**Issue:** Issuing 1099-K or 1099-NEC forms to contractors and platform users for IRS compliance
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
US payment processors must file 1099-K for users who receive more than 600 USD in payments. Marketplaces must issue #<number>-NEC to contractors paid over 600 USD annually.

## Pattern / Solution
Collect W-9 information at onboarding before first payout. Use Stripe's 1099 reporting feature for Connect platforms — Stripe files on your behalf for eligible connected accounts. For 1099-NEC, use a payroll provider or file via the IRS FIRE system.

## Gotchas
Stripe Connect handles 1099-K for eligible accounts automatically, but you must ensure W-9 info is collected and verified. Backup withholding (24%) applies if TIN is missing or invalid. State 1099 requirements may differ from federal.

## Related
stripe-connect-platform, sales-tax-us-states, vat-calculation-eu
