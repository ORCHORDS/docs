# PayPal vault setup-token lifecycle

**Issue:** PayPal vault setup tokens and payment tokens have different lifetimes and purposes. Reusing expired setup tokens, trusting browser returns, or storing funding details directly can duplicate consent or expose payment data.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Create tokens server-side for the intended customer/merchant and usage, persist only provider IDs and state, use idempotent operations, and exchange/confirm through documented flows. Verify final token status server-side and handle revocation, replacement, and account mismatch.

## Verification

Test approval cancellation, expiry, replay, duplicate callbacks, timeout-after-create, wrong customer/merchant, revoked instrument, sandbox/production confusion, and concurrent setup.

## Gotchas

A setup token is not a charge authorization or permanent payment token. Never log secrets or full funding credentials.

## Sources

- PayPal Developer, [Payment Method Tokens v3](https://developer.paypal.com/docs/api/payment-tokens/v3/)
