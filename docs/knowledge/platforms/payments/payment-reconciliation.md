# payment-reconciliation

**Issue:** Reconciling internal payment records against Stripe payouts and bank statements
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Stripe payouts are net of fees and may combine multiple transactions into one bank deposit. Without reconciliation, discrepancies between Stripe, your database, and the bank go undetected.

## Pattern / Solution
Use Stripe's Balance Transaction API to get a full itemized list of all charges, refunds, and fees within a payout. Match each balance transaction to your internal order records by charge ID. Sum charges, subtract fees and refunds, compare to payout amount. Flag any unmatched transactions for manual review.

## Gotchas
Stripe can split payouts across multiple bank transfers for large volumes. Refunds processed after a payout are netted against future payouts. Use Stripe Sigma or the /v1/balance_transactions endpoint with the payout parameter to scope transactions to a specific payout.

## Related
bank-statement-matching, payment-audit-logging, accounting-integration-quickbooks, xero-integration-payments
