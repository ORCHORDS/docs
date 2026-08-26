# one-click-upsell

**Issue:** Implementing post-purchase upsells where the customer can accept without re-entering payment details
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Post-purchase upsells convert at high rates when they do not require re-entering payment info. The customer's payment method from the initial purchase must be reused for the upsell charge.

## Pattern / Solution
After a successful payment_intent, retrieve the payment_method from the PaymentIntent object. Create a new PaymentIntent with confirm=true, payment_method, customer, and off_session=true. If 3DS is triggered, handle the requires_action state with a confirmation prompt.

## Gotchas
Off-session charges may be declined if 3DS is required and you cannot redirect. Store setup_future_usage='off_session' on the initial PaymentIntent to signal intent to reuse. High-value upsells may trigger additional friction.

## Related
order-bumps, stripe-payment-intents, stripe-payment-elements
