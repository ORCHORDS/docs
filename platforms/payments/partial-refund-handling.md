# partial-refund-handling

**Issue:** Processing partial refunds for line items, prorations, or goodwill credits
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Partial refunds are common for returns of individual items, goodwill gestures, or billing errors. Tracking partial refund amounts and remaining refundable balance requires careful bookkeeping.

## Pattern / Solution
Call Stripe POST /v1/refunds with amount in cents less than the original charge amount. Store each refund in a local refunds table with payment_id, amount, reason, and timestamp. Compute remaining_refundable as original_amount minus SUM of refunds. For invoices, use credit notes via POST /v1/credit_notes.

## Gotchas
Multiple partial refunds are allowed up to the original charge amount. Stripe credit notes are separate from refunds — a credit note adjusts the invoice but does not move money unless a refund is also issued.

## Related
refund-policy-implementation, stripe-invoice-customization, stripe-proration-logic
