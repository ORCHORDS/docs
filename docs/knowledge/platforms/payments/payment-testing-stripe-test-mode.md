# payment-testing-stripe-test-mode

**Issue:** Testing payment flows end-to-end using Stripe test mode and test card numbers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Payment flows are hard to test without triggering real charges. Stripe test mode provides a complete sandbox that mimics production behavior including webhooks, 3DS, and decline scenarios.

## Pattern / Solution
Use test API keys (sk_test_xxx, pk_test_xxx). Test card 4242424242424242 succeeds. 4000000000000002 declines. 4000002500003155 triggers 3DS authentication. 4000000000000341 simulates attaching successfully but failing on first charge. Use Stripe CLI to forward webhooks locally: stripe listen --forward-to localhost:3000/webhooks.

## Gotchas
Test mode webhooks have different event IDs than production — do not mix environments. Stripe CLI webhook forwarding shows all events including those from other sessions in your account. Always use environment variables to switch between test and live keys — never hardcode.

## Related
stripe-webhook-setup, stripe-webhook-signature-verification, stripe-payment-intents, stripe-checkout-session
