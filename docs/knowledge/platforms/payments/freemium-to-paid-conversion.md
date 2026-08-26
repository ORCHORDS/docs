# freemium-to-paid-conversion

**Issue:** Converting free users to paying customers at the moment of upgrade
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Freemium users upgrading to paid hit checkout cold — no stored payment method, no billing history. The upgrade flow must be fast and frictionless to maximize conversion.

## Pattern / Solution
Show pricing page with clear value props. On upgrade click, create a Stripe Customer if not exists, then redirect to Stripe Checkout or embed Stripe Elements. On payment success, immediately provision the paid plan. Send a confirmation email within seconds.

## Gotchas
Do not gate the upgrade behind email verification — the user is already authenticated. Pre-fill the email field in checkout from the user account. If the user had a trial, apply any remaining trial days as a discount coupon on the subscription.

## Related
stripe-checkout-session, free-trial-credit-card-required, stripe-coupon-discount, stripe-customer-portal
