# Stripe Adaptive Pricing presentment reconciliation

**Issue:** With Adaptive Pricing, the customer can see and pay a localized amount while the integration’s base currency remains different. Reading only legacy conversion fields or assuming displayed amount equals settlement creates support and accounting errors.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Persist the Checkout Session and resulting payment evidence with both integration-currency totals and customer presentment details exposed by the pinned Stripe API version. Fulfillment remains bound to verified session/payment status, not a browser-displayed amount.

## Controls

- Pin and test the Stripe API version used by webhooks.
- Read `presentment_details` where the current version provides it; do not depend on deprecated legacy fields.
- Record currency, amount, fee context, refund currency behavior, and provider IDs with integer minor units.
- Keep manual currency prices and Adaptive Pricing precedence explicit.
- Disclose localized amount and conversion fee behavior before confirmation.
- Reconcile refunds and disputes in both operational and accounting views.
- Validate unsupported session configurations and fall back to base currency.
- Never calculate entitlement quantity from formatted price text.

## Verification

Test supported and unsupported countries/currencies, manual price overrides, subscriptions, discounts, tax, refunds, disputes, webhook replay, and API-version upgrade fixtures. Compare Checkout display, Session fields, Charge, refund, payout, and ledger entries.

## Gotchas

Availability and restrictions vary by business region and integration type. Currency minor units differ. Adaptive Pricing manages conversion presentation; it does not eliminate settlement, fee, tax, or refund accounting.

## Sources

- [Stripe Adaptive Pricing](https://docs.stripe.com/payments/currencies/localize-prices/adaptive-pricing)
- [Stripe Adaptive Pricing presentment-details changelog](https://docs.stripe.com/changelog/basil/2025-03-31/add_presentment_details)
- [Stripe local presentment comparison](https://docs.stripe.com/payments/currencies/localize-prices)
