# Stripe ConfirmationToken server policy

**Issue:** A server trusts amount, shipping, return URL, or business metadata from client confirmation data because payment details arrived through a Stripe ConfirmationToken.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

ConfirmationTokens package client-collected payment confirmation details for supported Stripe flows. Retrieve/use them server-side while deriving amount, currency, customer, order, and allowed payment behavior from authoritative application state.

**Source:** [Stripe ConfirmationToken API](https://docs.stripe.com/api/confirmation_tokens)

## Controls

- create/finalize orders server-side before confirmation;
- bind a token to the authenticated checkout attempt;
- use idempotency keys for PaymentIntent creation/update;
- allowlist token-derived fields the flow accepts;
- never expose secret API keys;
- reconcile final status through webhooks/retrieval.

## Verification

Test token reuse/expiry, wrong customer/cart, price change, duplicate submit, unsupported payment method, required action, cancellation, and webhook reordering.

## Gotchas

A ConfirmationToken is not payment success or authorization for an amount. Client-secret possession is not application authentication. Supported fields/flows depend on API version.
