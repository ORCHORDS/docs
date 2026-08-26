# Stripe Subscription Pending Update Atomicity

**Issue:** A subscription change becomes effective even though the required invoice payment fails, or local entitlements switch before Stripe applies a payment-dependent update.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

For supported subscription updates that must apply only after payment succeeds, use Stripe's pending-update behavior (`payment_behavior=pending_if_incomplete`) and only supported parameters. Persist the intended change separately from the currently effective subscription. Treat `pending_update` as a provisional state with an expiry, invoice, request idempotency key, and desired entitlement delta.

Drive access from fetched Stripe subscription/invoice state after verified webhooks, not from the update API response or client redirect. On payment success, reconcile the applied subscription; on failure or expiry, retain old access and surface a retry/requote flow. Serialize concurrent plan changes per subscription.

## Verification

Test immediate success, authentication-required payment, hard decline, asynchronous processing, pending-update expiry, webhook replay/out-of-order delivery, customer retry, a second change while pending, cancellation, tax/discount differences, and API-version changes. Confirm old entitlements remain active until Stripe actually applies the update.

## Gotchas

Only a subset of subscription update fields supports pending updates. An unpaid invoice and a pending update are related but not interchangeable states. Retrying with changed parameters can create a different economic outcome; re-preview and obtain confirmation when totals change.

## Sources

- [Stripe — Pending updates](https://docs.stripe.com/billing/subscriptions/pending-updates)
- [Stripe — Subscription webhooks and states](https://docs.stripe.com/billing/subscriptions/webhooks)
