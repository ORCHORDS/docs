# Stripe Entitlements as an Access Projection

**Issue:** Granting product access directly from checkout success or subscription status can drift from Stripe's effective entitlement state during upgrades, downgrades, trials, pauses, and asynchronous billing changes.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Map Stripe products to features in a reviewed entitlement configuration. Treat the active-entitlement summary event as an invalidation signal, verify its webhook signature from the raw body, then retrieve or consume the supported entitlement state for the correct customer/account context.

Project that provider state into a local access table transactionally. Store the source event/version, feature key, effective state, and reconciliation timestamp. Make repeated or out-of-order events idempotent; an older event must not overwrite a newer projection. Authorization reads the local projection through a fail policy appropriate to the feature, not a synchronous Stripe request on every user action.

Keep billing identity mapping separate from login identity and require tenant ownership checks. Reconcile active entitlements periodically and after webhook outages. Audit manual overrides with an expiry and owner.

## Verification

Test new subscription, trial, payment failure, plan swap, quantity change, cancellation now/period-end, pause/resume, refund/dispute policy, duplicate and reordered events, missing customer mapping, and Stripe outage. Prove access changes once, within the stated propagation objective, and reconciliation repairs a dropped event.

## Gotchas

Entitlements describe features, not authentication. Checkout completion alone is not durable proof of continuing access. Define business policy for grace periods explicitly rather than inferring it from delivery timing.

## Sources

- [Stripe Entitlements](https://docs.stripe.com/billing/entitlements)
- [Stripe active entitlements API](https://docs.stripe.com/api/entitlements/active-entitlement)
- [Stripe webhook security](https://docs.stripe.com/webhooks)
