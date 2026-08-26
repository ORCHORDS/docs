# Stripe CustomerSession client-secret scope

**Issue:** A payment UI reuses a CustomerSession client secret across users, carts, or long periods, exposing saved-payment capabilities beyond the intended checkout.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

Stripe CustomerSessions configure customer-facing component access to saved payment methods. Create them server-side for the authenticated Stripe Customer and enable only required component features.

**Source:** [Stripe CustomerSession API](https://docs.stripe.com/api/customer_sessions)

## Controls

- authorize user-to-Customer binding before creation;
- enable the minimum component/features;
- deliver the client secret only to the intended client session;
- never log or persist it as a reusable credential;
- regenerate after account/role changes;
- keep charges and mutations server/webhook authoritative.

## Verification

Test wrong customer, account switch, expired/replayed secret, concurrent tabs, disabled feature, deleted payment method, logout, and network retry.

## Gotchas

The client secret scopes Stripe component behavior, not platform authorization. Session creation does not verify a payment method or complete payment. Treat secrets as sensitive and ephemeral.
