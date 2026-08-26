# bank-statement-matching

**Issue:** Matching Stripe payouts to bank statement lines for accurate bookkeeping
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Bank statements show a single net deposit per Stripe payout, while Stripe has hundreds of underlying transactions. Matching the two requires careful reconciliation against the payout ID.

## Pattern / Solution
Download bank statements as CSV. Fetch all Stripe payouts for the period via GET /v1/payouts. Match by amount and arrival_date. For each matched payout, pull the balance transactions (GET /v1/balance_transactions?payout=po_xxx) to get the itemized breakdown for journal entry posting.

## Gotchas
Bank processing can delay Stripe payouts by 1-2 business days from the expected arrival date. Failed payouts return funds to Stripe balance — they do not appear on bank statements. Stripe payouts in non-USD currencies convert at mid-market rate and the converted amount may differ from expected.

## Related
payment-reconciliation, accounting-integration-quickbooks, xero-integration-payments
