# Stripe cash-balance reconciliation

**Issue:** Incoming bank-transfer funds reach a Stripe customer cash balance but are matched to the wrong customer, automatically reconciled unexpectedly, or treated as paid before invoice allocation is authoritative.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

Stripe cash balances and customer balance transactions require processor-side reconciliation. Model inbound funding, unapplied funds, invoice application, reversal/refund, and webhook delivery as separate states.

**Source:** [Stripe customer cash balance reconciliation](https://docs.stripe.com/payments/customer-balance/reconcile-cash-balance)

## Controls

- key records by Stripe customer, cash-balance transaction, invoice, and currency;
- retrieve authoritative objects server-side after relevant webhooks;
- apply idempotency to manual reconciliation operations;
- restrict manual allocation and record operator reason/audit evidence;
- maintain an internal double-entry projection without inventing processor state.

## Verification

Test exact, under, over, multiple-open-invoice, wrong-reference, multi-currency, duplicate webhook, manual reconciliation, reversal, and delayed bank events. Reconcile Stripe totals to bank/payout evidence and the internal ledger.

## Gotchas

Available cash is not automatically earned revenue. Automatic reconciliation behavior depends on configuration and references. Webhook order is not guaranteed; never infer finality from a client page.
