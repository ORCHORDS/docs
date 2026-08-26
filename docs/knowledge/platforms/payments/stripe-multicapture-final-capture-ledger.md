# Stripe multicapture and final-capture ledger control

**Issue:** A platform captures one shipment from a manually authorized PaymentIntent and assumes the remainder stays available. Stripe treats the capture as final unless the request explicitly preserves the remainder, or the payment method is ineligible, so later shipments cannot be captured and the internal ledger overstates authorized funds.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published; capability-gate by payment method and account

## Problem and applicability

Stripe multicapture can allow multiple captures against one eligible card authorization. It is different from incremental authorization: multicapture consumes an existing authorized amount in parts, while incremental authorization attempts to increase that amount.

Use it for supported separate-fulfilment flows that genuinely need more than one capture. Do not use it to conceal an unknown total or extend an authorization deadline.

## Controls and implementation

1. Create the PaymentIntent with manual capture and request the multicapture feature using Stripe's documented request option. Treat the request as a preference, not proof of availability.
2. After authorization, inspect the PaymentIntent's latest Charge payment-method details for the returned multicapture availability. Fall back to one final capture or a new customer-approved payment flow when unavailable.
3. Before each capture, lock the order/payment aggregate and re-fetch authoritative amount_capturable, status, currency, capture deadline, and prior captures. Never calculate availability only from client order rows.
4. Send the amount_to_capture and set final_capture=false only when another eligible fulfilment remains. Stripe's default final behavior releases the remaining authorization, so make the finality decision explicit in code review and tests.
5. On the last capture, set final_capture=true or use the documented final behavior. Record released remainder separately from captured, refunded, disputed, and expired amounts.
6. Give every capture a stable operation identifier and Stripe idempotency key tied to the fulfilment fact. A timeout must retry the same logical capture, not create another.
7. Consume webhook events idempotently and reconcile them with API reads. Webhook order is not the ledger order, and a client response is not the settlement record.
8. Track provider limits, supported card/network/region conditions, and the original authorization expiry. Multiple captures do not create an unlimited count or extend the hold.
9. Prevent aggregate captures from exceeding the authorized/capturable amount and never ship beyond the current recorded authorization policy.

## Verification

Test feature available and unavailable, two and maximum-supported capture attempts, partial then final capture, accidental omitted final_capture, capture at exact remaining amount, over-capture, timeout and same-key retry, concurrent fulfilments, authorization expiry, cancellation, refund after multiple captures, dispute, and out-of-order webhooks.

Assert the invariant that captured plus currently capturable plus released/expired remainder reconciles to provider-authoritative authorization movements, with currency minor-unit handling tested separately.

## Gotchas

- Multicapture and incremental authorization solve different problems and can have different eligibility.
- final_capture defaults can release the remainder; never rely on memory of SDK defaults.
- Authorization validity still expires under network and payment-method rules.
- Provider maximum capture counts and support can change; enforce returned capability and current docs.

## Official sources

- [Stripe — Capture a payment multiple times](https://docs.stripe.com/payments/multicapture)
- [Stripe — Place a hold on a payment method](https://docs.stripe.com/payments/place-a-hold-on-a-payment-method)
