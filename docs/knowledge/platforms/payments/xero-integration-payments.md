# xero-integration-payments

**Issue:** Syncing Stripe payments to Xero for accounting and reconciliation
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Xero has a different API model than QuickBooks. Xero uses bank transactions and bank rules for reconciliation rather than direct invoice matching.

## Pattern / Solution
Use the Xero API to create Invoices for Stripe charges and Payments against those invoices. For each Stripe payout, create a BankTransaction in Xero matching the payout amount. Use Xero bank rules to auto-match Stripe payout descriptions. Tools: Amaka, Synder, or a custom Xero SDK integration.

## Gotchas
Xero's bank feed and manual entries can conflict — decide on one source of truth. Xero has API rate limits (60 calls per minute for Partner apps). Test reconciliation logic against a Xero demo company before production rollout.

## Related
accounting-integration-quickbooks, payment-reconciliation, bank-statement-matching
