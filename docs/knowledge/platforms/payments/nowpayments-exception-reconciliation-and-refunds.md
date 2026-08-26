# nowpayments-exception-reconciliation-and-refunds

**Issue:** NOWPayments payments that are underpaid, sent on the wrong network or in the wrong asset, expired, or stopped for review are handled as normal successful orders or disappear into support queues.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

A customer sends an amount below the required minimum, pays an unexpected asset/network, or completes a deposit after expiry. Support cannot determine whether the order is recoverable, what the customer should be told, or whether a refund is provider-managed, merchant-managed, or impossible.

## Root cause

Crypto payment exceptions are business-state exceptions, not parsing errors. Provider payment status, original order state, received asset/network, expected amount, and support/reconciliation evidence must remain linked. NOWPayments documents dynamic minimum amounts, exception cases such as wrong-network or wrong-asset deposits, and support/refund processes; merchant policy still determines entitlement and fulfilment.

**Source:** [NOWPayments payment FAQ](https://nowpayments.io/help/payments) and [NOWPayments help centre](https://nowpayments.io/help).

## Fix

- model exception states explicitly: underpaid, overpaid, expired, wrong asset, wrong network, stopped/review, refund requested, refunded, and unrecoverable;
- reconcile every exception against the provider payment/purchase record and the server-created payment intent;
- define a customer-facing policy for tolerance, time window, fees, manual review, and any refund eligibility before enabling the payment method;
- require authenticated support access and a non-sensitive case record; do not accept unverified wallet-address changes over unauthenticated channels;
- make refund or adjustment actions idempotent, dual-reviewed where material, and tied to the original order/payment identifiers;
- periodically reconcile provider payment history against unresolved local exceptions.

## Verification

- An underpayment cannot unlock fulfilment and enters a visible exception workflow.
- A wrong-network or wrong-asset deposit is never automatically treated as the expected asset.
- An expired payment followed by a late deposit is reconciled under the documented policy.
- A repeated support request cannot issue duplicate refund or credit actions.
- Reconciliation reports unmatched provider records and unresolved local cases.

## Gotchas

- “Refundable” is not the same as “automatically refundable”; network, asset, provider, and verification constraints can apply.
- Never put wallet addresses, identity documents, or raw support evidence in broad-access logs.
- Do not promise a customer a provider outcome until the provider record and the merchant policy agree.

## Related

- `payments/nowpayments-callback-payment-intent-integrity.md`
- `payments/nowpayments-multi-payment-order-aggregation.md`
- `patterns/idempotency-keys.md`
