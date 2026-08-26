# payment-error-handling

**Issue:** Handling payment API errors gracefully with correct user messaging and retry logic
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Payment failures surface as declined cards, network timeouts, or Stripe API errors. Each error type requires different handling — some are user-fixable, others require silent retry, and some indicate a fraud signal.

## Pattern / Solution
Catch Stripe errors by type: StripeCardError (card declined — show the decline_code to user), StripeRateLimitError (retry with exponential backoff), StripeInvalidRequestError (bug in your integration — alert the dev team), StripeAPIError (Stripe server issue — retry). Map decline codes (insufficient_funds, do_not_honor, card_velocity_exceeded) to user-friendly messages.

## Gotchas
Never expose raw Stripe error messages to end users — they contain technical details. The generic_decline code covers many cases where the issuer will not reveal the reason. Log all errors with the Stripe request_id for support escalation. Do not retry card_declined synchronously — it will not succeed.

## Related
stripe-payment-intents, stripe-smart-retries, stripe-failed-payment-retry, fraud-detection-signals
