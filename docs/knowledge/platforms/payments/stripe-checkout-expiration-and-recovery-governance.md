# Stripe Checkout Expiration and Recovery Governance

**Issue:** Expired Checkout Sessions retain inventory reservations or trigger repeated abandonment messages; recovery links are treated as proof of payment or sent without marketing consent.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Choose `expires_at` from the inventory/payment policy within Stripe's allowed window, and handle `checkout.session.expired` idempotently. Release reservations through an atomic order-state transition keyed by the Session ID. If recovery is enabled, store the recovery-link expiry and bind the resulting session/order through server-side identifiers.

Send abandonment messages only under the applicable consent and suppression rules. Deduplicate by customer/order campaign, cap frequency, and never log the recovery URL because it is a bearer-like navigation capability. Fulfill solely from verified payment/Checkout webhooks and current server-side object state, never from a recovery redirect.

## Verification

Test automatic and manual expiration, webhook replay and delay, a completion racing expiration, inventory release retry, multiple abandoned sessions for one customer, absent consent/email/recovery URL, expired recovery link, promotion-code policy, and successful recovered checkout. Confirm only one reservation release and one allowed message occur.

## Gotchas

Checkout's ordinary default expiration and the recovery URL's validity are different timelines. An expired original Session is not paid. Customer email can be absent from the expired event payload, and consent rules may prohibit contact. Manual expiration should pass through the same state machine as timed expiration.

## Sources

- [Stripe — Recover abandoned carts](https://docs.stripe.com/payments/checkout/abandoned-carts)
- [Stripe — Manage limited inventory with Checkout expiration](https://docs.stripe.com/payments/checkout/managing-limited-inventory)
