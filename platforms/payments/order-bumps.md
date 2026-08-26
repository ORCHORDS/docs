# order-bumps

**Issue:** Adding pre-purchase add-ons to checkout that increase order value without a separate flow
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Order bumps are checkboxes or toggles on the checkout page that add items to the order. They must update the payment amount in real time before the charge is submitted.

## Pattern / Solution
When the order bump checkbox is toggled, call your backend to update the PaymentIntent amount. With Stripe Elements, update the PaymentIntent amount via the API before calling stripe.confirmPayment(). Never update the amount client-side — always go through your server.

## Gotchas
Stripe does not allow updating a PaymentIntent amount to 0. If the bump makes the total 0, switch to a coupon approach. Tax must be recalculated when the order bump is added. Stripe Checkout does not support in-page modifications — use Elements for dynamic bumps.

## Related
one-click-upsell, stripe-payment-elements, stripe-tax-calculation
