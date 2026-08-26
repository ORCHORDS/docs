# paypal-subscriptions

**Issue:** Setting up recurring billing plans with PayPal Billing Agreements and Subscriptions API
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
PayPal subscriptions use a separate API from one-time payments. Plans must be created first, then subscriptions activated. Webhook events differ from Stripe's model.

## Pattern / Solution
Create a Plan with billing cycles via POST /v1/billing/plans. Activate the plan. Create a Subscription referencing the plan ID. Handle BILLING.SUBSCRIPTION.ACTIVATED, PAYMENT.SALE.COMPLETED, and BILLING.SUBSCRIPTION.CANCELLED webhooks to sync local state.

## Gotchas
Trial periods require a separate trial billing cycle with total_cycles=1. PayPal does not emit a webhook on the initial charge. Subscription status can be APPROVAL_PENDING until user approves via redirect.

## Related
paypal-integration-patterns, paypal-webhooks, stripe-subscription-lifecycle
