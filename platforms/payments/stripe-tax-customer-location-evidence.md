# Stripe Tax customer-location evidence

**Issue:** Tax calculation uses a stale billing address or IP-derived guess without tracking which customer-location evidence Stripe accepted.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented; tax policy requires qualified review

Stripe Tax determines customer location from supported address and payment evidence. Collect only needed fields, validate them at checkout, and retain the calculation/transaction evidence required for reconciliation.

**Source:** [Stripe Tax customer locations](https://docs.stripe.com/tax/customer-locations)

## Controls

- configure address collection appropriate to the sale and jurisdiction;
- pass consistent customer, shipping, billing, and payment-method data;
- handle location validation failures before finalization;
- keep product tax codes and registrations independent from location evidence;
- minimize retained personal data while meeting record obligations;
- require qualified review for ambiguous cases.

## Verification

Test billing/shipping mismatch, digital/physical goods, saved customer changes, incomplete address, tax ID, cross-border payment, refund, subscription renewal, and non-Stripe channels.

## Gotchas

Customer location is not the same as merchant registration or product taxability. IP alone may be insufficient. Stripe configuration does not replace legal determination or filing reconciliation.
