# paypal-webhooks

**Issue:** Verifying and handling PayPal webhook events reliably
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
PayPal webhooks require server-side signature verification using the PayPal API — there is no static secret like Stripe. Events can arrive out of order and may duplicate.

## Pattern / Solution
Call POST /v1/notifications/verify-webhook-signature with the raw headers and body. Check verification_status === 'SUCCESS'. Store processed event IDs in a deduplication table keyed on resource.id + event_type.

## Gotchas
PayPal sandbox and production use different base URLs. The verification call itself counts against API rate limits. Webhooks do not guarantee ordering — always query the resource directly for authoritative state.

## Related
paypal-integration-patterns, paypal-subscriptions, stripe-webhook-idempotency
