# Stripe incremental authorization and capture deadline control

**Issue:** A business increases an existing card authorization but treats it as a new authorization window, leading to missed captures or unclear fulfilment limits.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

## Root cause

Incremental authorization can increase an existing authorized amount for eligible payment flows. A failed increment does not remove the amount already authorized, and an increment does not extend the original authorization validity period. Capture decisions must therefore use the current authoritative capture deadline, not an assumed new window.

**Sources:**

- [Stripe incremental authorizations](https://docs.stripe.com/payments/incremental-authorization)
- [Stripe authorization holds and manual capture](https://docs.stripe.com/payments/place-a-hold-on-a-payment-method)

## Fix

- use incremental authorization only for a documented eligible scenario and payment method;
- persist the original authorization, each requested/approved increment, the current capturable amount, and the provider-returned capture deadline;
- schedule fulfilment and capture from the current deadline; do not infer that an increment extends it;
- if an increment fails, decide explicitly whether to fulfil only up to the existing authorized amount, obtain a new payment method, or cancel;
- bind each capture to a fulfilment fact and use idempotency for every provider call;
- reconcile final captures, reversals, and expired holds against orders and customer communication.

## Verification

- A successful increment changes only the capturable amount permitted by the provider.
- A failed increment leaves the prior authorization available for the permitted capture path.
- Capture scheduling uses the returned deadline and alerts before expiry.
- Duplicate increment/capture requests do not create duplicate customer charges or fulfilments.
- Partial fulfilment, cancellation, and expired-hold paths have an owned customer and ledger outcome.

## Gotchas

- Eligibility, amount caps, and authorization windows vary by payment method and network.
- An authorization is not settlement; do not recognize final revenue or irreversible fulfilment solely from the hold.
- Never expose authorization identifiers or customer payment details in logs.

## Related

- `payments/stripe-payment-intents.md`
- `payments/stripe-webhook-idempotency.md`
- `patterns/idempotency-keys.md`
