# nowpayments-multi-payment-order-aggregation

**Issue:** A customer completes one order through multiple NOWPayments deposits, but the application treats each deposit as an independent order or fulfils before the total is satisfied.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

A customer pays part of an order in one asset and another part later or in a different asset. The order remains incorrectly unpaid, is fulfilled twice, or is fulfilled after an underpayment because the application has no aggregate purchase state.

## Root cause

NOWPayments supports several payments for one order (“purchases”). Provider payment records are individual deposits; the merchant still needs a server-side purchase aggregate that defines expected value, permitted currencies, rate/valuation policy, expiry, and the exact condition for fulfilment.

**Source:** [NOWPayments API overview](https://nowpayments.io/help/what-is/what-is-api) and [NOWPayments purchases guidance](https://nowpayments.io/help/dashboard/how-to-view-past-payments-and-purchases).

## Fix

- create one immutable purchase aggregate before accepting the first deposit;
- attach every provider payment only after validating its purchase/order reference and intent policy;
- record each accepted contribution separately with its provider ID, status, amount, asset/network, valuation timestamp, and reconciliation state;
- calculate fulfillment from the aggregate using a documented valuation and tolerance policy, not from a single callback;
- make fulfilment an idempotent one-way transition and preserve an audit record of every contribution;
- define expiry, partial-payment, overpayment, wrong-asset, and refund/escalation procedures before launch.

## Verification

- A two-part payment reaches fulfilled only after the aggregate condition is met.
- Duplicate or late IPNs cannot double-count a contribution.
- An underpayment remains pending or follows the stated exception flow.
- A wrong-asset or wrong-network deposit cannot silently satisfy the order.
- Reconciliation of provider history and local aggregate detects missing or unmatched deposits.

## Gotchas

- Do not hard-code a fiat/crypto conversion assumption without documenting when the rate is selected.
- A customer reference is not sufficient as an authorization boundary; bind deposits to a server-created purchase.
- Avoid returning a “paid” UI state based only on client-side wallet confirmation.

## Related

- `payments/nowpayments-callback-payment-intent-integrity.md`
- `payments/crypto-payments-integration.md`
- `patterns/idempotency-keys.md`
