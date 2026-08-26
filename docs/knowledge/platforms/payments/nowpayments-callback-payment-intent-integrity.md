# nowpayments-callback-payment-intent-integrity

**Issue:** A NOWPayments IPN callback can be accepted without proving it belongs to a persisted checkout intent, leading to incorrect order fulfillment, duplicate side effects, or status regression.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

A payment callback reaches the application with a provider payment ID and status, but the system cannot reliably tie it to the original customer, order, expected amount, currency/network, or fulfillment state. Retries and out-of-order updates cause repeated fulfillment or a completed payment to move backwards.

## Root cause

IPNs are status notifications, not proof that an arbitrary request should create or fulfill an order. NOWPayments documents a secret used to verify IPN authenticity and provides payment-status lookup; the merchant must still bind a provider payment to a server-created, immutable payment intent and apply a monotonic state transition.

**Source:** [NOWPayments — IPN](https://nowpayments.io/help/what-is/what-is-ipn) and [API/payment status overview](https://nowpayments.io/help/what-is/what-is-api).

## Fix

- create and persist a payment intent before requesting a provider payment; record order ID, payer, expected amount, price currency, pay currency/network policy, expiration, and a unique merchant reference;
- bind the provider payment ID to that intent once, under a uniqueness constraint;
- verify every IPN against the provider’s documented secret/signature mechanism before parsing it into business state;
- fetch or reconcile payment status from the provider when callback authenticity, payload completeness, or transition ordering is uncertain;
- process callbacks idempotently using the provider payment ID plus a durable event or status record;
- allow only documented forward transitions; terminal fulfillment happens once after the business-defined confirmed/finished condition;
- retain non-sensitive evidence and reconciliation outcomes; never log API keys, IPN secrets, wallet details beyond operational need, or raw credential-bearing payloads.

## Verification

- **Binding:** a callback for an unknown or mismatched provider payment ID cannot fulfill any order.
- **Authenticity:** a modified callback or invalid signature is rejected before state mutation.
- **Ordering:** repeated and out-of-order callbacks cannot regress a terminal state or duplicate fulfillment.
- **Recovery:** a dropped callback is reconciled through the provider payment-status API and results in one deterministic final state.
- **Amount:** a partial, underpaid, wrong-currency, or expired payment follows an explicit exception path.

## Gotchas

- A valid callback does not override the order’s expected amount, currency, or fulfillment policy.
- Crypto-network confirmations and provider statuses have different timing; document the business condition for fulfillment.
- Do not use a client-supplied order reference as the sole authority for fulfillment.

## Related

- `payments/crypto-payments-integration.md`
- `patterns/idempotency-keys.md`
- `patterns/idempotency-reservation-lease-recovery.md`
