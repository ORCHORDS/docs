# free-trial-credit-card-required

**Issue:** Collecting card details during free trial signup without charging immediately
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Requiring a card for free trials improves paid conversion rates but increases signup friction. The card must be stored securely without being charged until the trial ends.

## Pattern / Solution
Create a SetupIntent (not PaymentIntent) during trial signup. Use stripe.confirmSetup() on the frontend with the setup_intent_client_secret. On success, attach the resulting PaymentMethod to the Customer. When the trial ends, create a Subscription with the stored payment method.

## Gotchas
SetupIntents may require 3DS — handle requires_action. Some cards decline SetupIntents (prepaid, international). The stored card may expire before trial ends — implement card expiry notifications. GDPR requires disclosing that payment info is stored.

## Related
stripe-trial-periods, stripe-subscription-lifecycle, card-expiry-handling, stripe-payment-elements
