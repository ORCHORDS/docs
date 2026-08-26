# nowpayments-invoice-lifecycle-and-late-deposits

**Issue:** An application treats a NOWPayments invoice, an individual payment, and a later repeat deposit as the same mutable payment record.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

An invoice is an order-facing container, while individual payments have their own lifecycle and identifiers. Late or repeated deposits can produce new provider payment records. Redirect completion is a user-interface event, not proof that a local order may be fulfilled.

**Source:** [NOWPayments — invoices and payments](https://nowpayments.zendesk.com/hc/en-us/articles/18393446018461-Invoices-and-payments).

## Fix

- persist immutable links among local order, local intent, provider invoice, and every provider payment ID;
- model payment lifecycle separately from the commercial order lifecycle;
- define explicit handling for payment expiry, late deposits, repeat deposits, and fixed-rate quote expiry;
- reconcile provider history on a schedule, not only when an IPN arrives;
- require the verified provider payment state and local amount/currency policy before fulfilment;
- route late or unmatched deposits to an auditable manual-review state.

## Verification

- A repeated deposit receives a distinct provider-payment record and cannot overwrite the original.
- A late deposit cannot auto-fulfil an expired order without the documented policy check.
- A dropped notification is discovered by reconciliation.
- A browser redirect alone never marks an order paid.

## Related

- `payments/nowpayments-callback-payment-intent-integrity.md`
- `payments/nowpayments-multi-payment-order-aggregation.md`
