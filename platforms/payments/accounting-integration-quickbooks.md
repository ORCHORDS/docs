# accounting-integration-quickbooks

**Issue:** Syncing Stripe payment data to QuickBooks for automated bookkeeping
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Manual entry of Stripe transactions into QuickBooks is error-prone and time-consuming. Automated sync must correctly map charges to income accounts, fees to expense accounts, and refunds to credit memos.

## Pattern / Solution
Use the official Stripe plus QuickBooks integration or a tool like Synder or Pilot. For custom integration: use QBO API to create SalesReceipts for charges, Expenses for Stripe fees, and RefundReceipts for refunds. Map Stripe metadata (product, customer) to QBO classes and customers.

## Gotchas
Stripe payouts must be reconciled against bank deposits in QuickBooks — the payout amount (net of fees) must match the bank entry. Multi-currency transactions require proper exchange rate handling in QBO. Test with a sandbox QBO account before touching production books.

## Related
xero-integration-payments, payment-reconciliation, bank-statement-matching, revenue-recognition-saas
